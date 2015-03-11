# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool
from .carrier import Carrier, TestConnectionStart, TestConnection


def register():
    Pool.register(
        Carrier,
        TestConnectionStart,
        module='shipping_dhl_de', type_='model'
    )
    Pool.register(
        TestConnection,
        module='shipping_dhl_de', type_='wizard'
    )
