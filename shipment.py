# -*- coding: utf-8 -*-
"""
    shipment.py

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import requests

from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool
from trytond.wizard import Wizard, StateView, Button
from sale import DHL_DE_PRODUCTS

__metaclass__ = PoolMeta
__all__ = [
    'ShipmentOut', 'GenerateShippingLabel', 'ShippingDHLDE',
]

STATES = {
    'readonly': Eval('state') == 'done',
    'required': Bool(Eval('is_dhl_de_shipping')),
}


class ShipmentOut:
    "Shipment Out"
    __name__ = 'stock.shipment.out'

    is_dhl_de_shipping = fields.Function(
        fields.Boolean('Is DHL (DE) Shipping', readonly=True),
        'get_is_dhl_de_shipping'
    )
    dhl_de_product_code = fields.Selection(
        DHL_DE_PRODUCTS, 'DHL DE Product Code', states=STATES,
        depends=['is_dhl_de_shipping', 'state']
    )

    def get_is_dhl_de_shipping(self, name):
        """
        Ascertains if the shipping is done using DHL (DE)
        """
        return self.carrier and self.carrier.carrier_cost_method == 'dhl_de'

    @fields.depends('is_dhl_de_shipping', 'carrier')
    def on_change_carrier(self):
        """
        Show/Hide dhl de Tab in view on change of carrier
        """
        res = super(ShipmentOut, self).on_change_carrier()

        res['is_dhl_de_shipping'] = self.carrier and \
            self.carrier.carrier_cost_method == 'dhl_de'

        return res

    def _get_weight_uom(self):
        """
        Return uom for DHL DE
        """
        UOM = Pool().get('product.uom')
        if self.is_dhl_de_shipping:
            return UOM.search([('symbol', '=', 'kg')])[0]
        return super(ShipmentOut, self)._get_weight_uom()  # pragma: no cover

    def _get_dhl_de_shipment_details(self, client):
        """
        Return `ns0:ShipmentDetailsType`
        """
        Date = Pool().get('ir.date')

        shipment_details = client.factory.create('ns0:ShipmentDetailsDDType')

        shipment_details.ProductCode = self.dhl_de_product_code
        shipment_details.ShipmentDate = Date.today().isoformat()

        # TODO: add customs value in DeclaredValueOfGoods
        dhl_de_account_no = self.carrier.dhl_de_account_no
        shipment_details.EKP = dhl_de_account_no[:10]
        shipment_details.Attendance = {
            'partnerID': dhl_de_account_no[-2:]
        }

        # Appear on Label
        shipment_details.CustomerReference = self.customer.code or \
            self.customer.id

        # XXX: One shipment item/box for 1 customer shipment
        shipment_item = client.factory.create('ns0:ShipmentItemDDType')
        shipment_item.WeightInKG = self.package_weight

        # TODO: Add package type
        shipment_item.PackageType = 'PK'
        shipment_details.ShipmentItem = [shipment_item]

        return shipment_details

    def _get_dhl_de_shipper_type(self, client):
        """
        Return `ns0:ShipperDDType`
        """
        shipper_type = client.factory.create('ns0:ShipperDDType')
        shipper_type.Company = {
            'Company': {
                'name1': self.company.party.name
            }
        }
        from_address = self._get_ship_from_address()
        if not from_address:  # pragma: no cover
            self.raise_user_error('Shipper address is missing')

        shipper_type.Address = from_address.as_dhl_de_address(client)

        shipper_type.Communication = \
            from_address._get_dhl_de_communication_type(client)
        return shipper_type

    def _get_dhl_de_receiver_type(self, client):
        """
        Return `ns0:ShipperDDType`
        """
        receiver_type = client.factory.create('ns0:ReceiverDDType')
        to_address = self.delivery_address

        receiver_name = to_address.name or self.customer.name
        if ' ' in receiver_name:
            fname, lname = receiver_name.split(' ', 1)
        else:  # pragma: no cover
            fname, lname = receiver_name, '-'
        receiver_type.Company = {
            'Person': {
                'firstname': fname,
                'lastname': lname
            }
        }
        receiver_type.Address = to_address.as_dhl_de_address(client)

        receiver_type.Communication = \
            to_address._get_dhl_de_communication_type(client)
        return receiver_type

    def _get_dhl_de_shipment_type(self, client):
        """
        Return `ns0:Shipment` element for this shipment
        """
        shipment_type = client.factory.create('ns0:Shipment')
        shipment_type.ShipmentDetails = \
            self._get_dhl_de_shipment_details(client)
        shipment_type.Shipper = self._get_dhl_de_shipper_type(client)
        shipment_type.Receiver = self._get_dhl_de_receiver_type(client)
        return shipment_type

    def make_dhl_de_labels(self):
        """
        Make labels for the shipment using DHL DE

        :return: Tracking number as string
        """
        Attachment = Pool().get('ir.attachment')

        if self.state not in ('packed', 'done'):  # pragma: no cover
            self.raise_user_error('invalid_state')

        if not self.is_dhl_de_shipping:  # pragma: no cover
            self.raise_user_error('wrong_carrier', 'DHL_DE')

        if self.tracking_number:  # pragma: no cover
            self.raise_user_error('tracking_number_already_present')

        client = self.carrier.get_dhl_de_client()
        shipment_order_type = client.factory.create('ns0:ShipmentOrderDDType')
        shipment_order_type.SequenceNumber = '%s' % self.id
        shipment_order_type.Shipment = self._get_dhl_de_shipment_type(client)

        response = self.carrier.send_dhl_de_create_shipment_shipment_dd(
            [shipment_order_type]
        )

        creation_state, = response.CreationState
        if creation_state.StatusCode != '0':  # pragma: no cover
            self.raise_user_error('\n'.join(creation_state.StatusMessage))
        tracking_number = \
            creation_state.ShipmentNumber.shipmentNumber
        label_url = creation_state.Labelurl

        self.tracking_number = unicode(tracking_number)
        self.save()

        try:
            pdf_label = requests.get(label_url)
        except:  # pragma: no cover
            self.raise_user_error(
                'Error in downloading label from %s' % label_url)
        Attachment.create([{
            'name': "%s.pdf" % (
                tracking_number,
            ),
            'data': pdf_label.content,
            'resource': '%s,%s' % (self.__name__, self.id)
        }])
        return tracking_number


class GenerateShippingLabel(Wizard):
    'Generate Labels'
    __name__ = 'shipping.label'

    dhl_de_config = StateView(
        'shipping.label.dhl_de',
        'shipping_dhl_de.shipping_dhl_de_config_wizard_view_form',
        [
            Button('Back', 'start', 'tryton-go-previous'),
            Button('Continue', 'generate', 'tryton-go-next'),
        ]
    )

    def default_dhl_de_config(self, data):
        shipment = self.start.shipment

        return {
            'product_code': shipment.dhl_de_product_code,
            'is_international_shipping': shipment.is_international_shipping,
        }

    def transition_next(self):  # pragma: no cover
        state = super(GenerateShippingLabel, self).transition_next()

        if self.start.carrier.carrier_cost_method == 'dhl_de':
            return 'dhl_de_config'
        return state

    def update_shipment(self):
        shipment = super(GenerateShippingLabel, self).update_shipment()

        if self.start.carrier.carrier_cost_method == 'dhl_de':
            shipment.dhl_de_product_code = self.dhl_de_config.product_code

        return shipment


class ShippingDHLDE(ModelView):
    'Generate Labels'
    __name__ = 'shipping.label.dhl_de'

    product_code = fields.Selection(
        DHL_DE_PRODUCTS, 'DHL DE Product Code', required=True
    )
    is_international_shipping = fields.Boolean("Is International Shipping")
