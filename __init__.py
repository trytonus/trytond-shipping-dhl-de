# -*- coding: utf-8 -*-
"""
    __init__.py

"""
from trytond.pool import Pool
from carrier import Carrier, TestConnectionStart, TestConnection
from party import Address
from sale import Sale, SaleConfiguration
from shipment import ShipmentOut, GenerateShippingLabel, ShippingDHLDE


def register():
    Pool.register(
        Address,
        Carrier,
        SaleConfiguration,
        Sale,
        ShipmentOut,
        ShippingDHLDE,
        TestConnectionStart,
        module='shipping_dhl_de', type_='model'
    )
    Pool.register(
        TestConnection,
        GenerateShippingLabel,
        module='shipping_dhl_de', type_='wizard'
    )
