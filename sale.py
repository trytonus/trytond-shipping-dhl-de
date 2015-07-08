# -*- coding: utf-8 -*-
"""
    sale.py

"""
from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelView, Workflow
from trytond.pyson import Eval, Bool, And

__all__ = ['Sale', 'SaleConfiguration']
__metaclass__ = PoolMeta

STATES = {
    'readonly': Eval('state') == 'done',
    'required': Bool(Eval('is_dhl_de_shipping')),
}
INTERNATIONAL_STATES = {
    'readonly': Eval('state') == 'done',
    'required': And(
        Bool(Eval('is_dhl_de_shipping')),
        Bool(Eval('is_international_shipping'))
    ),
}
INTERNATIONAL_DEPENDS = [
    'state', 'is_international_shipping', 'is_dhl_de_shipping'
]

DHL_DE_PRODUCTS = [
    (None, ''),
    ('BPI', 'Weltpaket'),
    ('EPN', 'DHL Paket'),
    # Features which are not implemented yet.
    # ('EPI', 'DHL Europaket'),
    # ('EUP', 'GHL Europlus'),
    # ('EXI (td)', 'Express Ident'),
    # ('EXP (td)', 'DHL Express Paket'),
    # ('OFP (td)', 'DHL Officepack'),
    # ('RPN', 'Regional Paket AT'),
]

DHL_DE_EXPORT_TYPES = [
    (None, ''),
    ('0', 'Other'),
    ('1', 'Gift'),
    ('2', 'Sample'),
    ('3', 'Documents'),
    ('4', 'Goods Return'),
]

DHL_DE_INCOTERMS = [
    (None, ''),
    ('DDU', 'DDU'),
    ('CIP', 'CIP'),
    ('DDP', 'DDP'),
]


class SaleConfiguration:
    'Sale Configuration'
    __name__ = 'sale.configuration'

    dhl_de_product_code = fields.Selection(
        DHL_DE_PRODUCTS, 'DHL DE PRODUCT CODE'
    )
    dhl_de_export_type = fields.Selection(
        DHL_DE_EXPORT_TYPES, 'DHL DE Export Type'
    )
    dhl_de_terms_of_trade = fields.Selection(
        DHL_DE_INCOTERMS, 'Terms of Trade (incoterms)'
    )

    @staticmethod
    def default_dhl_de_product_code():
        return 'EPN'


class Sale:
    "Sale"
    __name__ = 'sale.sale'

    is_dhl_de_shipping = fields.Function(
        fields.Boolean('Is Shipping', readonly=True),
        'get_is_dhl_de_shipping'
    )

    dhl_de_product_code = fields.Selection(
        DHL_DE_PRODUCTS, 'DHL DE Product Code', states=STATES, depends=[
            'state', 'is_dhl_de_shipping'
        ]
    )
    dhl_de_export_type = fields.Selection(
        DHL_DE_EXPORT_TYPES, 'DHL DE Export Type', states=INTERNATIONAL_STATES,
        depends=INTERNATIONAL_DEPENDS
    )
    dhl_de_export_type_description = fields.Char(
        'Export Type Description', states={
            'required': And(
                Eval('state').in_(
                    ['confirmed', 'processing', 'done']
                ),
                Bool(Eval('is_dhl_de_shipping')),
                Bool(Eval('is_international_shipping'))
            ),
            'readonly': Eval('state') == 'done',
        },
        depends=INTERNATIONAL_DEPENDS
    )
    dhl_de_terms_of_trade = fields.Selection(
        DHL_DE_INCOTERMS, 'Terms of Trade (incoterms)',
        states=INTERNATIONAL_STATES, depends=INTERNATIONAL_DEPENDS
    )

    @staticmethod
    def default_dhl_de_product_code():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.dhl_de_product_code

    @staticmethod
    def default_dhl_de_export_type():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.dhl_de_export_type

    @staticmethod
    def default_dhl_de_terms_of_trade():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.dhl_de_terms_of_trade

    @classmethod
    @ModelView.button
    @Workflow.transition('quotation')
    def quote(cls, sales):
        """
        Downstream implementation of quote method which provides a default
        value to the dhl_de_export_type field.
        """
        for sale in sales:
            if sale.is_dhl_de_shipping and sale.is_international_shipping:
                sale.set_dhl_de_export_type_description()
                sale.save()

        super(Sale, cls).quote(sales)

    def set_dhl_de_export_type_description(self):
        """
        This method sets a default export type description if none is set
        """
        if self.dhl_de_export_type_description:
            return

        if self.description:
            self.dhl_de_export_type_description = self.description
        else:
            self.dhl_de_export_type_description = ', '.join(
                map(
                    lambda line: line.type == 'line' and line.product.name,
                    self.lines
                )
            )

    def get_is_dhl_de_shipping(self, name):
        """
        Ascertains if the sale is done using DHL (DE)
        """
        return self.carrier and self.carrier.carrier_cost_method == 'dhl_de'

    @fields.depends('is_dhl_de_shipping', 'carrier')
    def on_change_carrier(self):
        """
        Show/Hide dhl de Tab in view on change of carrier
        """
        res = super(Sale, self).on_change_carrier()

        res['is_dhl_de_shipping'] = self.carrier and \
            self.carrier.carrier_cost_method == 'dhl_de'

        return res

    def _get_shipment_sale(self, Shipment, key):
        """
        Downstream implementation which adds dhl-specific fields to the unsaved
        Shipment record.
        """
        ShipmentOut = Pool().get('stock.shipment.out')

        shipment = super(Sale, self)._get_shipment_sale(Shipment, key)

        if Shipment == ShipmentOut and self.is_dhl_de_shipping:
            shipment.dhl_de_product_code = self.dhl_de_product_code
            shipment.dhl_de_export_type = self.dhl_de_export_type
            shipment.dhl_de_export_type_description = \
                self.dhl_de_export_type_description
            shipment.dhl_de_terms_of_trade = self.dhl_de_terms_of_trade

        return shipment
