# -*- encoding: utf-8 -*-
"""
    Customizes party address to have address in correct format for DHL API

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool, PoolMeta

__all__ = ['Address']
__metaclass__ = PoolMeta


class Address:
    "Address"
    __name__ = "party.address"

    def as_dhl_de_address(self, client):
        """
        Returns the address as ns1:NativeAddressType
        """
        address = client.factory.create('ns1:NativeAddressType')

        address.careOfName = self.name
        address.streetName = '\n'.join(
            # Non empty street parts
            filter(None, (self.street, self.streetbis))
        )

        if self.zip:
            country = self.country and self.country.code or None
            zip_type = client.factory.create("ns1:ZipType")
            if country == 'DE':
                zip_type.germany = self.zip
            elif country == 'GB':
                zip_type.england = self.zip
            else:
                zip_type.other = self.zip

            address.Zip = zip_type

        address.city = self.city

        if self.subdivision:
            address.Origin = self.subdivision.as_dhl_de_country_type(client)

        return address


class Subdivision:
    "Subdivision"
    __name__ = 'country.subdivision'

    def as_dhl_de_country_type(self, client):
        """
        Returns the subdivision as ns1:CountryType
        """
        # It is strange that the type is called country while in reality
        # it is subdivision.
        country = client.factory.create('ns1:CountryType')
        country.country = self.country.name
        country.countryISOCode = self.country.code
        country.state = self.name
        return country
