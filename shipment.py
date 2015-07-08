# -*- coding: utf-8 -*-
"""
    shipment.py

"""
import requests

from sale import INTERNATIONAL_STATES, INTERNATIONAL_DEPENDS
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool
from trytond.wizard import Wizard, StateView, Button
from sale import DHL_DE_PRODUCTS, DHL_DE_EXPORT_TYPES, DHL_DE_INCOTERMS
from carrier import log

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
    dhl_de_export_type = fields.Selection(
        DHL_DE_EXPORT_TYPES, 'DHL DE Export Type', states=INTERNATIONAL_STATES,
        depends=INTERNATIONAL_DEPENDS
    )
    dhl_de_export_type_description = fields.Char(
        'Export Type Description', states=INTERNATIONAL_STATES,
        depends=INTERNATIONAL_DEPENDS
    )
    dhl_de_terms_of_trade = fields.Selection(
        DHL_DE_INCOTERMS, 'Terms of Trade (incoterms)',
        depends=INTERNATIONAL_DEPENDS, states=INTERNATIONAL_STATES
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

        shipment_items = []

        for package in self.packages:
            shipment_item = client.factory.create('ns0:ShipmentItemDDType')
            shipment_item.WeightInKG = package.weight

            # TODO: Add package type
            shipment_item.PackageType = 'PK'
            shipment_items.append(shipment_item)

        shipment_details.ShipmentItem = shipment_items

        # Multipack service can be used for DHL Paket only
        if len(self.packages) > 1 and self.dhl_de_product_code == 'EPN':
            # Mark as Multipack service
            shipment_service = client.factory.create('ns0:ShipmentServiceDD')
            shipment_service_group = client.factory.create(
                'ns0:DDServiceGroupDHLPaketType')
            shipment_service_group.Multipack = True
            shipment_service.ServiceGroupDHLPaket = shipment_service_group
            shipment_details.Service = [shipment_service]

        # TODO: Implement Service

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

    def _get_dhl_de_export_invoice_date(self):
        """
        Return DHL DE Export Invoice Date

        Fallback from invoice_date > sale_date > today_date
        """
        Date = Pool().get('ir.date')

        try:
            invoice_date = \
                self.outgoing_moves[0].invoice_lines[0].invoice.invoice_date
        except IndexError:  # pragma: no cover
            invoice_date = None
        try:
            sale_date = self.outgoing_moves[0].sale.sale_date
        except IndexError:  # pragma: no cover
            sale_date = None

        return invoice_date or sale_date or Date.today()

    def _get_dhl_de_export_doc_type(self, client):
        """
        Return `ExportDocumentDDType`
        """
        export_type = client.factory.create('ns0:ExportDocumentDDType')
        export_type.InvoiceType = 'commercial'

        # XXX: Invoice Date
        export_type.InvoiceDate = \
            self._get_dhl_de_export_invoice_date().isoformat()

        # Export type
        #   (
        #       "0"="other", "1"="gift", "2"="sample", "3"="documents",
        #       "4"="goods return"
        #   ) (depends on chosen product -> only mandatory for BPI).
        #   Field length must be less than or equal to 40.
        export_type.ExportType = '0'
        export_type.ExportTypeDescription = self.dhl_de_export_type_description

        value = 0
        for move in self.outgoing_moves:
            value += float(move.product.customs_value_used) * move.quantity

        # Element provides terms of trades,
        # i.e. incoterms codes like DDU, CIP et al. Field length must be = 3.
        export_type.TermsOfTrade = self.dhl_de_terms_of_trade

        # Amount of shipment positions. Multiple positions not allowed for EUP
        # and EPI, only BPI allows amount > 1. Field length must be less than
        # or equal to 22.
        export_type.Amount = 1
        description = ','.join([
            move.product.name for move in self.outgoing_moves
        ])
        export_type.Description = description

        package_weight = sum([p.weight for p in self.packages])
        from_address = self._get_ship_from_address()
        export_type.CountryCodeOrigin = from_address.country.code
        export_type.CustomsValue = value
        export_type.CustomsCurrency = self.company.currency.code
        export_type.ExportDocPosition = {
            'Description': description,
            'CountryCodeOrigin': from_address.country.code,
            'Amount': 1,
            'NetWeightInKG': package_weight,
            'GrossWeightInKG': package_weight,
            'CustomsValue': value,
            'CustomsCurrency': self.company.currency.code,
        }

        return export_type

    def _get_dhl_de_shipment_type(self, client):
        """
        Return `ns0:Shipment` element for this shipment
        """
        shipment_type = client.factory.create('ns0:Shipment')
        shipment_type.ShipmentDetails = \
            self._get_dhl_de_shipment_details(client)
        shipment_type.Shipper = self._get_dhl_de_shipper_type(client)
        shipment_type.Receiver = self._get_dhl_de_receiver_type(client)
        if self.is_international_shipping:
            shipment_type.ExportDocument = self._get_dhl_de_export_doc_type(
                client)
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

        if not self.packages:
            self.raise_user_error("no_packages", error_args=(self.id,))

        client = self.carrier.get_dhl_de_client()
        shipment_order_type = client.factory.create('ns0:ShipmentOrderDDType')
        shipment_order_type.SequenceNumber = '%s' % self.id
        shipment_order_type.Shipment = self._get_dhl_de_shipment_type(client)

        response = self.carrier.send_dhl_de_create_shipment_shipment_dd(
            [shipment_order_type]
        )

        creation_state, = response.CreationState
        if creation_state.StatusCode != '0':  # pragma: no cover
            log.debug(client.last_sent())
            log.debug(client.last_received())
            self.raise_user_error('\n'.join(creation_state.StatusMessage))
        tracking_number = \
            creation_state.ShipmentNumber.shipmentNumber
        label_url = creation_state.Labelurl

        self.tracking_number = unicode(tracking_number)
        self.save()

        # DHL returns the tracking number of each piece in reverse order
        piece_info = creation_state.PieceInformation
        piece_info.reverse()
        for package, package_info in zip(self.packages, piece_info):
            package.tracking_number = package_info.PieceNumber.licensePlate
            package.save()

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
            'export_type': shipment.dhl_de_export_type,
            'export_type_description': shipment.dhl_de_export_type_description,
            'terms_of_trade': shipment.dhl_de_terms_of_trade,
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
            if shipment.is_international_shipping:  # pragma: no cover
                shipment.dhl_de_export_type = self.dhl_de_config.export_type
                shipment.dhl_de_export_type_description = \
                    self.dhl_de_config.export_type_description
                shipment.dhl_de_terms_of_trade = \
                    self.dhl_de_config.terms_of_trade

        return shipment


class ShippingDHLDE(ModelView):
    'Generate Labels'
    __name__ = 'shipping.label.dhl_de'

    product_code = fields.Selection(
        DHL_DE_PRODUCTS, 'DHL DE Product Code', required=True
    )
    is_international_shipping = fields.Boolean("Is International Shipping")
    export_type = fields.Selection(
        DHL_DE_EXPORT_TYPES, 'DHL DE Export Type',
        states={
            'required': Bool(Eval('is_international_shipping'))
        }, depends=['is_international_shipping']
    )
    export_type_description = fields.Char('Export Type Description')
    terms_of_trade = fields.Selection(
        DHL_DE_INCOTERMS, 'Terms of Trade (incoterms)',
        states={
            'required': Bool(Eval('is_international_shipping'))
        }, depends=['is_international_shipping']
    )
