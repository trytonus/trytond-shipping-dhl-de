"""
Generate a shipment label using WSDL
"""
import os
import traceback
from datetime import datetime

import suds
from suds.client import Client
from suds.sax.element import Element
from suds.plugin import MessagePlugin

# flake8: noqa

SHIPPER_STREET = "Heinrich-Bruening-Str.";
SHIPPER_STREETNR = "7";
SHIPPER_CITY = "Bonn";
SHIPPER_ZIP = "53113";
SHIPPER_COUNTRY_CODE = "DE";
SHIPPER_CONTACT_EMAIL = "max@muster.de";
SHIPPER_CONTACT_NAME = "Max Muster";
SHIPPER_CONTACT_PHONE = "030244547777778";
SHIPPER_COMPANY_NAME = "Deutsche Post IT Brief GmbH";
ENCODING = "UTF8";
MAJOR_RELEASE = "1";
MINOR_RELEASE = "0";
SDF = 'Y-m-d';
DD_PROD_CODE = "BPI";
TEST_EKP = "5000000008";
PARTNER_ID = "01";
SHIPMENT_DESC = "Interessanter Artikel";
TD_SHIPMENT_REF = "DDU";
TD_VALUE_GOODS = 250;
TD_CURRENCY = "EUR";
TD_ACC_NUMBER_EXPRESS = "144405785";
TD_DUTIABLE = "1";


RECEIVER_FIRST_NAME = "Kai";
RECEIVER_LAST_NAME = "Wahn";
RECEIVER_LOCAL_STREET = "Marktplatz";
RECEIVER_LOCAL_STREETNR = "1";
RECEIVER_LOCAL_CITY = "Stuttgart";
RECEIVER_LOCAL_ZIP = "70173";
RECEIVER_LOCAL_COUNTRY_CODE = "DE";

RECEIVER_WWIDE_STREET = "Chung Hsiao East Road.";
RECEIVER_WWIDE_STREETNR = "55";
RECEIVER_WWIDE_CITY = "Taipeh";
RECEIVER_WWIDE_ZIP = "100";
RECEIVER_WWIDE_COUNTRY = "Taiwan";
RECEIVER_WWIDE_COUNTRY_CODE = "TW";

RECEIVER_CONTACT_EMAIL = "kai@wahn.de";
RECEIVER_CONTACT_NAME = "Kai Wahn";
RECEIVER_CONTACT_PHONE = "+886 2 27781-8";
RECEIVER_COMPANY_NAME = "Klammer Company";
DUMMY_SHIPMENT_NUMBER = "0000000";

EXPORT_REASON = "Sale";
SIGNER_TITLE = "Director Asia Sales";
EXPORT_TYPE = "P";
INVOICE_NUMBER = "200601xx417";
INVOICE_TYPE = "commercial";
DUMMY_AIRWAY_BILL = "0000000000";


client = Client(
    "https://cig.dhl.de/cig-wsdls/com/dpdhl/wsdl/geschaeftskundenversand-api/1.0/geschaeftskundenversand-api-1.0.wsdl",  # noqa
    username=os.environ['DHL_DE_USERNAME'],
    password=os.environ['DHL_DE_PASSWORD'],
    location='https://cig.dhl.de/services/sandbox/soap'
)

class VersionNS(MessagePlugin):
    def marshalled(self, context):
        shipment_dd = context.envelope.getChild(
            'Body'
        ).getChild('CreateShipmentDDRequest')

        version = shipment_dd.getChild('Version')
        version.setPrefix('ns0')

        shipment_details = shipment_dd.getChild('ShipmentOrder').getChild(
            'Shipment').getChild('ShipmentDetails')
        shipment_details.getChild('EKP').setPrefix('ns0')
        shipment_details.getChild('Attendance').getChild('partnerID') \
            .setPrefix('ns0')

client.set_options(soapheaders=[{
    'user': 'geschaeftskunden_api',
    'signature': 'Dhl_ep_test1',
    'type': 0,
}], plugins=[VersionNS()])




def create_version():
    el = Element('Version')
    el.setPrefix('ns0')

    major_release = Element('majorRelease')
    major_release.setPrefix('ns0')
    major_release.setText('1')
    el.append(major_release)

    minor_release = Element('minorRelease')
    minor_release.setPrefix('ns0')
    minor_release.setText('18')
    el.append(minor_release)

    return {
        'majorRelease': '1',
        'minorRelease': '0',
    }

    return el


def create_default_shipment_item_dd_type():
    shipment_item = client.factory.create('ns0:ShipmentItemDDType')
    shipment_item.HeightInCM = '15'
    shipment_item.LengthInCM = '50'
    shipment_item.WeightInKG = '3'
    shipment_item.WidthInCM = '30'
    shipment_item.PackageType = 'PK'
    return shipment_item


def create_shipment_details_dd_type():
    """
    (ShipmentDetailsDDType){
       ProductCode = None
       ShipmentDate = None
       DeclaredValueOfGoods = None
       DeclaredValueOfGoodsCurrency = None
       EKP = None
       Attendance =
          (Attendance){
             partnerID = None
          }
       CustomerReference = None
       Description = None
       DeliveryRemarks = None
       ShipmentItem[] = <empty>
       Service[] = <empty>
       Notification[] = <empty>
       NotificationEmailText = None
       BankData =
          (BankType){
             accountOwner = None
             accountNumber = None
             bankCode = None
             bankName = None
             iban = None
             note = None
             bic = None
          }
     }
    """
    shipment_details = client.factory.create('ns0:ShipmentDetailsDDType')

    # XXX: Add 2 days ?
    shipment_details.ShipmentDate = datetime.today().date().isoformat()
    shipment_details.ProductCode = DD_PROD_CODE
    shipment_details.EKP = TEST_EKP
    shipment_details.Attendance.partnerID = PARTNER_ID
    shipment_details.Description = SHIPMENT_DESC
    shipment_details.ShipmentItem.append(
        create_default_shipment_item_dd_type()
    )

    shipment_details.Service = {
        'ServiceGroupBusinessPackInternational': dd_service_type_ecnomy()
    }
    return shipment_details


def as_dhl_de_address(mode='shipper'):
    """
    Returns the address as ns1:NativeAddressType
    """
    address = client.factory.create('ns1:NativeAddressType')
    if mode == 'shipper':
        address.streetName = SHIPPER_STREET
        address.streetNumber = SHIPPER_STREETNR

        zip_type = client.factory.create("ns1:ZipType")
        zip_type.germany = SHIPPER_ZIP
        address.Zip = zip_type

        address.city = SHIPPER_CITY

        country = client.factory.create('ns1:CountryType')
        country.countryISOCode = SHIPPER_COUNTRY_CODE
        address.Origin = country

    elif mode == 'receiver':
        #address.streetName = RECEIVER_LOCAL_STREET
        #address.streetNumber = RECEIVER_LOCAL_STREETNR

        #zip_type = client.factory.create("ns1:ZipType")
        #zip_type.germany = RECEIVER_LOCAL_ZIP
        #address.Zip = zip_type

        #address.city = RECEIVER_LOCAL_CITY

        #country = client.factory.create('ns1:CountryType')
        #country.countryISOCode = RECEIVER_LOCAL_COUNTRY_CODE
        #address.Origin = country

        address.streetName = RECEIVER_WWIDE_STREET
        address.streetNumber = RECEIVER_WWIDE_STREETNR

        zip_type = client.factory.create("ns1:ZipType")
        zip_type.other = RECEIVER_WWIDE_ZIP
        address.Zip = zip_type

        address.city = RECEIVER_WWIDE_CITY

        country = client.factory.create('ns1:CountryType')
        country.countryISOCode = RECEIVER_WWIDE_COUNTRY_CODE
        address.Origin = country

    return address


def create_shipper():
    """
    Return `ns0:ShipperDDType`
    """
    shipper_type = client.factory.create('ns0:ShipperType')
    shipper_type.Company = {
        'Company': {
            'name1': SHIPPER_COMPANY_NAME
        }
    }
    shipper_type.Address = as_dhl_de_address(mode='shipper')

    comm_type = client.factory.create('ns1:CommunicationType')
    comm_type.phone = SHIPPER_CONTACT_PHONE
    comm_type.email = SHIPPER_CONTACT_EMAIL
    comm_type.contactPerson = SHIPPER_CONTACT_NAME
    shipper_type.Communication = comm_type

    return shipper_type


def create_receiver():
    """
    Return `ns0:ShipperDDType`
    """
    receiver_type = client.factory.create('ns0:ReceiverDDType')

    receiver_type.Company = {
        'Person': {
            'firstname': RECEIVER_FIRST_NAME,
            'lastname': RECEIVER_LAST_NAME
        }
    }
    receiver_type.Address = as_dhl_de_address(mode='receiver')

    comm_type = client.factory.create('ns1:CommunicationType')

    comm_type.phone = RECEIVER_CONTACT_PHONE
    comm_type.email = RECEIVER_CONTACT_EMAIL

    comm_type.contactPerson = RECEIVER_CONTACT_NAME
    receiver_type.Communication = comm_type
    return receiver_type

def dd_service_type_ecnomy():
    service_type = client.factory.create(
        'ns0:DDServiceGroupBusinessPackInternationalType'
    )
    service_type.Economy = True
    return service_type

def export_doc_type():
    """
    Return `ExportDocumentDDType`
    """
    from datetime import datetime
    export_type = client.factory.create('ns0:ExportDocumentDDType')
    export_type.InvoiceType = 'commercial'
    export_type.InvoiceDate = datetime.now().date().isoformat()

    # Export type
    #   (
    #       "0"="other", "1"="gift", "2"="sample", "3"="documents",
    #       "4"="goods return"
    #   ) (depends on chosen product -> only mandatory for BPI).
    #   Field length must be less than or equal to 40.
    export_type.ExportType = '1'
    #export_type.ExportTypeDescription = SHIPMENT_DESC

    # Element provides terms of trades,
    # i.e. incoterms codes like DDU, CIP et al. Field length must be = 3. 
    export_type.TermsOfTrade = 'DDP'
    export_type.Amount = '22'

    export_type.Description = SHIPMENT_DESC
    export_type.CountryCodeOrigin = SHIPPER_COUNTRY_CODE
    export_type.CustomsValue = TD_VALUE_GOODS
    export_type.CustomsCurrency = TD_CURRENCY
    export_type.ExportDocPosition = {
        'Description': 'test descri',
        'CountryCodeOrigin': 'DE',
        'Amount': 22,
        'NetWeightInKG': 3,
        'GrossWeightInKG': 3,
        'CustomsValue': 12,
        'CustomsCurrency': 'EUR',
    }

    return export_type



def create_shipment():
    shipment_order_type = client.factory.create('ns0:ShipmentOrderDDType')
    shipment_order_type.SequenceNumber = 1
    shipment_order_type.LabelResponseType = "URL"

    shipment_type = client.factory.create('ns0:Shipment')
    shipment_type.ShipmentDetails = create_shipment_details_dd_type()
    shipment_type.Shipper = create_shipper()
    shipment_type.Receiver = create_receiver()
    shipment_type.ExportDocument = export_doc_type()

    shipment_order_type.Shipment = shipment_type

    try:
        print client.service.createShipmentDD(create_version(), shipment_order_type)
        print client.last_sent()
        print client.last_received()
        import pdb; pdb.set_trace()
    except suds.WebFault, exc:
        traceback.print_exc()
        print client.last_sent()
        print client.last_received()
        import pdb; pdb.set_trace()


if __name__ == '__main__':
    create_shipment()
