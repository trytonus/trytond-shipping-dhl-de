# -*- coding: utf-8 -*-
"""
    carrier.py

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from suds import WebFault
from suds.client import Client

from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelView
from trytond.pyson import Eval
from trytond.wizard import Wizard, StateView, Button

__all__ = ['Carrier', 'TestConnectionStart', 'TestConnection']
__metaclass__ = PoolMeta

STATES = {
    'required': Eval('carrier_cost_method') == 'dhl_de',
    'invisible': Eval('carrier_cost_method') != 'dhl_de'
}


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
    dhl_de_environment = fields.Selection([
        ('sandbox', 'Testing & Development (Sandbox)'),
        ('production', 'Production'),
    ], 'Environment', states=STATES, depends=['carrier_cost_method'])

    @classmethod
    def __setup__(cls):
        super(Carrier, cls).__setup__()

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
        Return the DPD client with the username and password set
        """
        location='https://cig.dhl.de/services/sandbox/soap'
        if self.dhl_de_environment == 'production':
            location='https://cig.dhl.de/services/production/soap'

        return Client(
            self.dhl_de_wsdl_url,
            username=self.dhl_de_username,
            password=self.dhl_de_password,
            location=location,
        )

    @classmethod
    @ModelView.button_action('shipping_dhl_de.wizard_test_connection')
    def test_dhl_de_credentials(cls, carriers):
        """
        Tests the connection. If there is a WebFault, raises an UserError
        """
        if len(carriers) != 1:
            cls.raise_user_error('Only one carrier can be tested at a time.')

        client = carriers[0].get_dhl_de_client()
        try:
            client.service.getVersion()
        except WebFault, exc:
            cls.raise_user_error(exc.fault)
        except Exception, exc:
            if exc.args and isinstance(exc.args[0], tuple):
                status, reason = exc.args[0]
                if status == 401:
                    cls.raise_user_error('Invalid Credentials')
                cls.raise_user_error(
                    'Status: %s\nReason: %s' % exc.args[0]
                )
            raise


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
