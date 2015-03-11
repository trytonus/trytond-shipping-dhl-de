# -*- coding: utf-8 -*-
"""
    shipment.py

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool, PoolMeta

__metaclass__ = PoolMeta
__all__ = [
    'ShipmentOut', 'GenerateShippingLabel'
]

STATES = {
    'readonly': Eval('state') == 'done',
}


class ShipmentOut:
    "Shipment Out"
    __name__ = 'stock.shipment.out'

    is_dhl_de_shipping = fields.Function(
        fields.Boolean('Is DHL (DE) Shipping', readonly=True),
        'get_is_dhl_de_shipping'
    )

    def get_is_dhl_de_shipping(self):
        """
        Ascertains if the shipping is done using DHL (DE)
        """
        return self.carrier and self.carrier.carrier_cost_method == 'dhl_de'
