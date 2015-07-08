# -*- coding: utf-8 -*-
"""
    carrier.py

"""
from decimal import Decimal

from suds import WebFault
from suds.client import Client
from suds.plugin import MessagePlugin

from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelView
from trytond.pyson import Eval
from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from logbook import Logger

log = Logger('shipping_dhl_de')

__all__ = ['Carrier', 'TestConnectionStart', 'TestConnection']
__metaclass__ = PoolMeta

STATES = {
    'required': Eval('carrier_cost_method') == 'dhl_de',
    'invisible': Eval('carrier_cost_method') != 'dhl_de'
}


class FixPrefix(MessagePlugin):
    """
    Suds client plugin to fix prefixes
    """
    def marshalled(self, context):
        shipment_dd = context.envelope.getChild(
            'Body'
        ).getChild('CreateShipmentDDRequest')

        shipment_dd.getChild('Version').setPrefix('ns0')
        shipment_details = shipment_dd.getChild('ShipmentOrder') \
            .getChild('Shipment').getChild('ShipmentDetails')
        shipment_details.getChild('EKP').setPrefix('ns0')
        shipment_details.getChild('Attendance').getChild('partnerID') \
            .setPrefix('ns0')


class Carrier:
    "Carrier"
    __name__ = "carrier"

    dhl_de_username = fields.Char(
        'Username', states=STATES, depends=['carrier_cost_method'],
        help="EntwickerID"
    )
    dhl_de_password = fields.Char(
        'Password', states=STATES, depends=['carrier_cost_method'],
        help="Application Token (Production)\nPortal Password(Staging)"
    )
    dhl_de_api_user = fields.Char(
        'API User', states=STATES, depends=['carrier_cost_method'],
        help="Intraship-User"
    )
    dhl_de_api_signature = fields.Char(
        'API Signature', states=STATES, depends=['carrier_cost_method'],
        help="IntrashipPasswort"
    )
    dhl_de_account_no = fields.Char(
        'Account Number', states=STATES, depends=['carrier_cost_method'],
        help="DHL Account Number (14 digit)"
    )
    dhl_de_environment = fields.Selection([
        ('sandbox', 'Testing & Development (Sandbox)'),
        ('production', 'Production'),
    ], 'Environment', states=STATES, depends=['carrier_cost_method'])

    def __init__(self, *args, **kwargs):
        super(Carrier, self).__init__(*args, **kwargs)
        self._dhl_de_version = None
        self._dhl_de_client = None

    @classmethod
    def __setup__(cls):
        super(Carrier, cls).__setup__()
        cls._error_messages.update({
            'dhl_de_test_conn_error':
                "Error while testing credentials from DHL DE: \n\n%s",
            'dhl_de_label_error':
                "Error while generating label from DHL DE: \n\n%s"
        })

        selection = ('dhl_de', 'DHL (DE)')
        if selection not in cls.carrier_cost_method.selection:
            cls.carrier_cost_method.selection.append(selection)

        cls._buttons.update({
            'test_dhl_de_credentials': {},
        })

        cls.dhl_de_wsdl_url = "https://cig.dhl.de/cig-wsdls/com/dpdhl/wsdl/geschaeftskundenversand-api/1.0/geschaeftskundenversand-api-1.0.wsdl"    # noqa

    @staticmethod
    def default_dhl_de_environment():
        return 'sandbox'

    def get_dhl_de_client(self):
        """
        Return the DHL DE client with the username and password set
        """
        if self._dhl_de_client is None:
            location = 'https://cig.dhl.de/services/sandbox/soap'
            if self.dhl_de_environment == 'production':  # pragma: no cover
                location = 'https://cig.dhl.de/services/production/soap'

            client = Client(
                self.dhl_de_wsdl_url,
                username=self.dhl_de_username,
                password=self.dhl_de_password,
                location=location,
            )
            self._dhl_de_client = client

        return self._dhl_de_client

    def get_dhl_de_version(self):
        if self._dhl_de_version is None:
            client = self.get_dhl_de_client()
            self._dhl_de_version = client.service.getVersion()

        return self._dhl_de_version

    def send_dhl_de_create_shipment_shipment_dd(self, shipment_orders):
        """
        Send ShipmentDD Request
        """
        version = self.get_dhl_de_version()
        client = self.get_dhl_de_client()
        client.set_options(soapheaders=[{
            'user': self.dhl_de_api_user,
            'signature': self.dhl_de_api_signature,
            'type': 0,
        }], plugins=[FixPrefix()])

        try:
            response = client.service.createShipmentDD(version, shipment_orders)
        except WebFault, exc:  # pragma: no cover
            log.debug(client.last_sent())
            log.debug(client.last_received())
            self.raise_user_error(
                'dhl_de_label_error', error_args=(exc.message, )
            )
        return response

    @classmethod
    @ModelView.button_action('shipping_dhl_de.wizard_test_connection')
    def test_dhl_de_credentials(cls, carriers):
        """
        Tests the connection. If there is a WebFault, raises an UserError
        """
        if len(carriers) != 1:  # pragma: no cover
            cls.raise_user_error('Only one carrier can be tested at a time.')

        client = carriers[0].get_dhl_de_client()
        try:
            client.service.getVersion()
        except WebFault, exc:  # pragma: no cover
            cls.raise_user_error(
                'dhl_de_test_conn_error', error_args=(exc.message, )
            )
        except Exception, exc:  # pragma: no cover
            if exc.args and isinstance(exc.args[0], tuple):
                status, reason = exc.args[0]
                if status == 401:
                    cls.raise_user_error('Invalid Credentials')
                cls.raise_user_error(
                    'Status: %s\nReason: %s' % exc.args[0]
                )
            raise

    def get_sale_price(self):
        """Estimates the shipment rate for the current shipment
        DHL DE dont provide and shipping cost, so here shipping_cost will be 0
        returns a tuple of (value, currency_id)
        :returns: A tuple of (value, currency_id which in this case is EUR)
        """
        Currency = Pool().get('currency.currency')
        Company = Pool().get('company.company')

        if self.carrier_cost_method != 'dhl_de':
            return super(Carrier, self).get_sale_price()  # pragma: no cover

        currency, = Currency.search([('code', '=', 'EUR')])
        company = Transaction().context.get('company')

        if company:
            currency = Company(company).currency

        return Decimal('0'), currency.id


class TestConnectionStart(ModelView):
    "Test Connection"
    __name__ = 'shipping_dhl_de.wizard_test_connection.start'


class TestConnection(Wizard):
    """
    Test Connection Wizard
    """
    __name__ = 'shipping_dhl_de.wizard_test_connection'

    start = StateView(
        'shipping_dhl_de.wizard_test_connection.start',
        'shipping_dhl_de.wizard_test_connection_view_form',
        [
            Button('Ok', 'end', 'tryton-ok'),
        ]
    )
