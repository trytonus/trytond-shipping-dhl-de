# -*- encoding: utf-8 -*-
"""
    Customizes party address to have address in correct format for DHL API

"""
from trytond.pool import PoolMeta

__all__ = ['Address']
__metaclass__ = PoolMeta


class Address:
    "Address"
    __name__ = "party.address"

    def _get_dhl_de_communication_type(self, client):
        """
        Return `CommunicationType`
        """
        comm_type = client.factory.create('ns1:CommunicationType')
        party = self.party

        if party.phone:
            comm_type.phone = party.phone
        if party.email:
            comm_type.email = party.email
        if party.fax:
            comm_type.fax = party.fax
        if party.mobile:
            comm_type.mobile = party.mobile
        if party.website:
            comm_type.internet = party.website

        comm_type.contactPerson = self.name or party.name
        return comm_type

    def as_dhl_de_address(self, client):
        """
        Returns the address as ns1:NativeAddressType
        """
        address = client.factory.create('ns1:NativeAddressType')

        address.careOfName = self.name
        address.streetName = self.street
        address.streetNumber = self.streetbis

        if self.zip:
            country = self.country and self.country.code or None
            zip_type = client.factory.create("ns1:ZipType")
            if country == 'DE':
                zip_type.germany = self.zip
            elif country == 'GB':  # pragma: no cover
                # TODO: Cover this in international shipping
                zip_type.england = self.zip
            else:
                zip_type.other = self.zip

            address.Zip = zip_type

        address.city = self.city

        if self.country:
            country = client.factory.create('ns1:CountryType')
            country.country = self.country.name
            country.countryISOCode = self.country.code
            if self.subdivision:
                # Field length must be less than or equal to 9.
                country.state = self.subdivision.name[:9]
            address.Origin = country

        return address
