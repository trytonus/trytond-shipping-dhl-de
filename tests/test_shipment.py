# -*- coding: utf-8 -*-
"""
    test_shipment

    Test dhl de Integration

"""
from decimal import Decimal
from time import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

import sys
import os
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction
from trytond.config import config
from trytond.exceptions import UserError
config.set('database', 'path', '.')

DIR = os.path.abspath(os.path.normpath(
    os.path.join(__file__, '..', '..', '..', '..', '..', 'trytond')
))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))


class TestDHLDEShipment(unittest.TestCase):
    """Test DHL DE Integration
    """

    def setUp(self):
        trytond.tests.test_tryton.install_module('shipping_dhl_de')
        self.Address = POOL.get('party.address')
        self.Sale = POOL.get('sale.sale')
        self.SaleLine = POOL.get('sale.line')
        self.SaleConfig = POOL.get('sale.configuration')
        self.Product = POOL.get('product.product')
        self.Uom = POOL.get('product.uom')
        self.Account = POOL.get('account.account')
        self.Category = POOL.get('product.category')
        self.Carrier = POOL.get('carrier')
        self.CarrierConfig = POOL.get('carrier.configuration')
        self.Party = POOL.get('party.party')
        self.PartyContact = POOL.get('party.contact_mechanism')
        self.PaymentTerm = POOL.get('account.invoice.payment_term')
        self.Country = POOL.get('country.country')
        self.Subdivision = POOL.get('country.subdivision')
        self.PartyAddress = POOL.get('party.address')
        self.StockLocation = POOL.get('stock.location')
        self.StockShipmentOut = POOL.get('stock.shipment.out')
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.IrAttachment = POOL.get('ir.attachment')
        self.User = POOL.get('res.user')
        self.Template = POOL.get('product.template')
        self.GenerateLabel = POOL.get('shipping.label', type="wizard")

        assert 'DHL_DE_USERNAME' in os.environ, \
            "DHL_DE_USERNAME missing. Hint:Use export DHL_DE_USERNAME=<string>"
        assert 'DHL_DE_PASSWORD' in os.environ, \
            "DHL_DE_PASSWORD missing. Hint:Use export DHL_DE_PASSWORD=<string>"

        self.username = os.environ['DHL_DE_USERNAME']
        self.password = os.environ['DHL_DE_PASSWORD']

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard"
        )

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _create_fiscal_year(self, date_=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date_ is None:
            date_ = datetime.utcnow().date()

        if not company:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date_.year,
            'code': 'account.invoice',
            'company': company
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date_.year,
            'start_date': date_ + relativedelta(month=1, day=1),
            'end_date': date_ + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date_.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else None

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def setup_defaults(self):
        """Method to setup defaults
        """
        # Create currency
        self.currency, = self.Currency.create([{
            'name': 'Euro',
            'code': 'EUR',
            'symbol': 'EUR',
        }])

        country_de, country_tw = self.Country.create([{
            'name': 'Germany',
            'code': 'DE',
        }, {
            'name': 'Taiwan',
            'code': 'TW',
        }])

        subdivision_bw, = self.Subdivision.create([{
            'name': 'Baden-Württemberg',
            'code': 'DE-BW',
            'type': 'state',
            'country': country_de.id,
        }])

        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
                'name': 'Deutsche Post IT Brief GmbH',
                'vat_number': '123456',
                'addresses': [('create', [{
                    'name': 'Max Muster',
                    'street': 'Heinrich-Bruening-Str.',
                    'streetbis': '7',
                    'zip': '53113',
                    'city': 'Bonn',
                    'country': country_de.id,
                }])],
                'contact_mechanisms': [('create', [{
                    'type': 'phone',
                    'value': '030244547777778',
                }, {
                    'type': 'email',
                    'value': 'max@muster.de',
                }, {
                    'type': 'fax',
                    'value': '030244547777778',
                }, {
                    'type': 'mobile',
                    'value': '9876543212',
                }, {
                    'type': 'website',
                    'value': 'example.com',
                }])],
            }])

        self.company, = self.Company.create([{
            'party': company_party.id,
            'currency': self.currency.id,
        }])

        self.User.write(
            [self.User(USER)], {
                'main_company': self.company.id,
                'company': self.company.id,
            }
        )

        CONTEXT.update(self.User.get_preferences(context_only=True))

        self._create_fiscal_year(company=self.company)
        self._create_coa_minimal(company=self.company)
        self.payment_term, = self._create_payment_term()

        account_revenue, = self.Account.search([
            ('kind', '=', 'revenue')
        ])

        # Create product category
        category, = self.Category.create([{
            'name': 'Test Category',
        }])

        uom_kg, = self.Uom.search([('symbol', '=', 'kg')])
        uom_cm, = self.Uom.search([('symbol', '=', 'cm')])
        uom_pound, = self.Uom.search([('symbol', '=', 'lb')])

        # Carrier Carrier Product
        carrier_product_template, = self.Template.create([{
            'name': 'Test Carrier Product',
            'category': category.id,
            'type': 'service',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'cost_price_method': 'fixed',
            'account_revenue': account_revenue.id,
            'products': [('create', self.Template.default_products())]
        }])

        carrier_product = carrier_product_template.products[0]

        # Create product
        template, = self.Template.create([{
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'account_revenue': account_revenue.id,
            'weight': .5,
            'weight_uom': uom_pound.id,
            'products': [('create', self.Template.default_products())]
        }])

        self.product = template.products[0]

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        values = {
            'party': carrier_party.id,
            'currency': self.currency.id,
            'carrier_product': carrier_product.id,
            'carrier_cost_method': 'dhl_de',
            'dhl_de_username': self.username,
            'dhl_de_password': self.password,
            'dhl_de_api_user': 'geschaeftskunden_api',
            'dhl_de_api_signature': 'Dhl_ep_test1',
            'dhl_de_account_no': '5000000008 72 01',
        }

        self.carrier, = self.Carrier.create([values])

        self.sale_party, self.sale_party2 = self.Party.create([{
            'name': 'Klammer Company',
            'vat_number': '123456',
            'addresses': [('create', [{
                'name': 'Kai Wahn',
                'street': 'Marktplatz',
                'streetbis': '1',
                'zip': '70173',
                'city': 'Stuttgart',
                'country': country_de.id,
                'subdivision': subdivision_bw.id,
            }])],
            'contact_mechanisms': [('create', [{
                'type': 'phone',
                'value': '+886 2 27781-8',
            }, {
                'type': 'email',
                'value': 'kai@wahn.de',
            }])],
        }, {
            'name': 'Klammer Company',
            'vat_number': '123456',
            'addresses': [('create', [{
                'name': 'John Wick',
                'street': 'Chung Hsiao East Road.',
                'streetbis': '55',
                'zip': '100',
                'city': 'Taipeh',
                'country': country_tw.id,
            }])],
            'contact_mechanisms': [('create', [{
                'type': 'phone',
                'value': '+886 2 27781-8',
            }, {
                'type': 'email',
                'value': 'kai@wahn.de',
            }])],
        }])
        sale_config = self.SaleConfig()
        sale_config.save()

    def create_sale(self, party):
        """
        Create and confirm sale order for party with default values.
        """
        with Transaction().set_context(company=self.company.id):

            # Create sale order
            sale_line = self.SaleLine(**{
                'type': 'line',
                'quantity': 1,
                'product': self.product,
                'unit_price': Decimal('10.00'),
                'description': 'Test Description1',
                'unit': self.product.template.default_uom,
            })
            sale = self.Sale(**{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
                'lines': [sale_line],
            })
            if self.company.party.addresses[0].country != \
                    sale.shipment_address.country:
                # International
                sale.dhl_de_product_code = 'BPI'
                sale.dhl_de_export_type = '0'
                sale.dhl_de_export_type_description = 'Export Description'
                sale.dhl_de_terms_of_trade = 'DDP'
            else:
                # Domestic: Defaults to EPN from SaleConfig
                pass

            sale.save()

            self.assertTrue(
                self.Sale(sale.id).on_change_carrier()['is_dhl_de_shipping']
            )

            self.StockLocation.write([sale.warehouse], {
                'address': self.company.party.addresses[0].id,
            })

            # Confirm and process sale order
            self.assertEqual(len(sale.lines), 1)
            self.Sale.quote([sale])
            self.Sale.confirm([sale])
            self.Sale.process([sale])

    def create_shipment_package(self, shipment):
        """
        Create a package for the shipment
        """
        Package = POOL.get('stock.package')
        ModelData = POOL.get('ir.model.data')

        type_id = ModelData.get_id(
            "shipping", "shipment_package_type"
        )

        package, = Package.create([{
            'shipment': '%s,%d' % (shipment.__name__, shipment.id),
            'type': type_id,
            'moves': [('add', shipment.outgoing_moves)],
        }])
        return package

    def test_0010_generate_dhl_de_labels(self):
        """Test case to generate DHL DE labels.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()
            self.Carrier.test_dhl_de_credentials([self.carrier])
            self.create_sale(self.sale_party)

            shipment, = self.StockShipmentOut.search([])
            self.assertTrue(
                self.StockShipmentOut(shipment.id).on_change_carrier().get(
                    'is_dhl_de_shipping'
                )
            )
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):
                # Test if UserError is raised as shipment has no packages
                with self.assertRaises(UserError):
                    shipment.make_dhl_de_labels()

                self.create_shipment_package(shipment)
                # Call method to generate labels.
                shipment.make_dhl_de_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(shipment.packages[0].tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0012_generate_dhl_de_labels_using_wizard(self):
        """
        Test case to generate DHL DE labels using wizard
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()
            self.create_sale(self.sale_party)

            shipment, = self.StockShipmentOut.search([])

            # Before generating labels, there is no tracking number generated
            # And no attachment created for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(
                company=self.company.id, active_id=shipment.id
            ):
                # Call method to generate labels.
                session_id, start_state, _ = self.GenerateLabel.create()

                generate_label = self.GenerateLabel(session_id)

                result = generate_label.default_start({})

                self.assertEqual(result['shipment'], shipment.id)
                self.assertEqual(result['carrier'], shipment.carrier.id)

                generate_label.start.shipment = shipment.id
                generate_label.start.override_weight = Decimal('0')
                generate_label.start.carrier = result['carrier']

                generate_label.transition_next()
                self.assertTrue(shipment.packages)
                self.assertEqual(len(shipment.packages), 1)
                result = generate_label.default_dhl_de_config({})

                self.assertEqual(
                    result['product_code'], shipment.dhl_de_product_code
                )

                generate_label.dhl_de_config.product_code = 'EPN'
                result = generate_label.default_generate({})

                self.assertEqual(
                    result['message'],
                    'Shipment labels have been generated via %s and saved as '
                    'attachments for the shipment' % (
                        shipment.carrier.carrier_cost_method.upper()
                    )
                )

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(shipment.packages[0].tracking_number)
            self.assertEqual(shipment.carrier, self.carrier)
            self.assertEqual(shipment.cost_currency, self.currency)
            self.assertEqual(shipment.dhl_de_product_code, 'EPN')
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0030_generate_dhl_de_international_labels(self):
        """Test case to generate DHL DE labels for international shipments.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            self.create_sale(self.sale_party2)

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])
            self.create_shipment_package(shipment)

            with Transaction().set_context(company=self.company.id):
                # Call method to generate labels.
                shipment.make_dhl_de_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(shipment.packages[0].tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0040_generate_dhl_de_labels_multiple_packages_using_wizard(self):
        """
        Test case to generate DHL DE labels using wizard
        """
        Package = POOL.get('stock.package')
        ModelData = POOL.get('ir.model.data')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()
            with Transaction().set_context(company=self.company.id):

                party = self.sale_party
                # Create sale order
                sale, = self.Sale.create([{
                    'reference': 'S-1001',
                    'payment_term': self.payment_term,
                    'party': party.id,
                    'invoice_address': party.addresses[0].id,
                    'shipment_address': party.addresses[0].id,
                    'carrier': self.carrier.id,
                    'lines': [
                        ('create', [{
                            'type': 'line',
                            'quantity': 1,
                            'product': self.product,
                            'unit_price': Decimal('10.00'),
                            'description': 'Test Description1',
                            'unit': self.product.template.default_uom,
                        }, {
                            'type': 'line',
                            'quantity': 2,
                            'product': self.product,
                            'unit_price': Decimal('10.00'),
                            'description': 'Test Description1',
                            'unit': self.product.template.default_uom,
                        }]),
                    ]
                }])

                self.StockLocation.write([sale.warehouse], {
                    'address': self.company.party.addresses[0].id,
                })

                # Confirm and process sale order
                self.assertEqual(len(sale.lines), 2)
                self.Sale.quote([sale])
                self.Sale.confirm([sale])
                self.Sale.process([sale])

            shipment = sale.shipments[0]

            type_id = ModelData.get_id(
                "shipping", "shipment_package_type"
            )

            package1, package2 = Package.create([{
                'shipment': '%s,%d' % (shipment.__name__, shipment.id),
                'type': type_id,
                'moves': [('add', [shipment.outgoing_moves[0]])],
            }, {
                'shipment': '%s,%d' % (shipment.__name__, shipment.id),
                'type': type_id,
                'moves': [('add', [shipment.outgoing_moves[1]])],
            }])
            # Before generating labels, there is no tracking number generated
            # And no attachment created for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(
                company=self.company.id, active_id=shipment.id
            ):
                # Call method to generate labels.
                session_id, start_state, _ = self.GenerateLabel.create()

                generate_label = self.GenerateLabel(session_id)

                result = generate_label.default_start({})

                self.assertEqual(result['shipment'], shipment.id)
                self.assertEqual(result['carrier'], shipment.carrier.id)

                generate_label.start.shipment = shipment.id
                generate_label.start.override_weight = Decimal('0')
                generate_label.start.carrier = result['carrier']

                result = generate_label.default_dhl_de_config({})

                self.assertEqual(
                    result['product_code'], shipment.dhl_de_product_code
                )

                generate_label.dhl_de_config.product_code = 'EPN'
                result = generate_label.default_generate({})

                self.assertEqual(
                    result['message'],
                    'Shipment labels have been generated via %s and saved as '
                    'attachments for the shipment' % (
                        shipment.carrier.carrier_cost_method.upper()
                    )
                )

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(package1.tracking_number)
            self.assertTrue(package2.tracking_number)
            self.assertNotEqual(
                package1.tracking_number, package2.tracking_number)
            self.assertEqual(shipment.carrier, self.carrier)
            self.assertEqual(shipment.cost_currency, self.currency)
            self.assertEqual(shipment.dhl_de_product_code, 'EPN')
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) == 1
            )

    def test_0050_sale_quotation(self):
        """
        Test how export type description field will be populated
        """
        StockLocation = POOL.get('stock.location')
        with Transaction().start(DB_NAME, USER, context=CONTEXT) as txn:
            self.setup_defaults()
            txn.set_context(company=self.company.id)

            StockLocation.write(
                StockLocation.search([('type', '=', 'warehouse')]), {
                    'address': self.sale_party.addresses[0].id,
                }
            )
            # Create sale order
            sale_line = self.SaleLine(**{
                'type': 'line',
                'quantity': 1,
                'product': self.product,
                'unit_price': Decimal('10.00'),
                'description': 'Test Description1',
                'unit': self.product.template.default_uom,
            })
            sale = self.Sale(**{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': self.sale_party2.id,
                'description': 'Sale Description',
                'invoice_address': self.sale_party2.addresses[0].id,
                'shipment_address': self.sale_party2.addresses[0].id,
                'carrier': self.carrier.id,
                'lines': [sale_line],
            })
            # International
            sale.dhl_de_product_code = 'BPI'
            sale.dhl_de_export_type = '0'
            sale.dhl_de_terms_of_trade = 'DDP'
            sale.save()

            # Description
            self.Sale.quote([sale])
            self.assertEqual(
                sale.dhl_de_export_type_description, sale.description
            )

            self.Sale.draft([sale])
            sale.description = None
            sale.dhl_de_export_type_description = None
            sale.save()

            # Product lines
            self.Sale.quote([sale])
            self.assertEqual(
                sale.dhl_de_export_type_description,
                ', '.join(
                    map(
                        lambda line: line.type == 'line' and line.product.name,
                        sale.lines
                    )
                )
            )

    def test_0060_sale_international_shipping(self):
        """
        Test that export_type_description is not required to quote-confirm-process sale
        when international shipping is not enabled.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT) as txn:
            self.setup_defaults()
            txn.set_context(company=self.company.id)

            # Create sale order
            sale_line = self.SaleLine(**{
                'type': 'line',
                'quantity': 1,
                'product': self.product,
                'unit_price': Decimal('10.00'),
                'description': 'Test Description1',
                'unit': self.product.template.default_uom,
            })
            sale = self.Sale(**{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': self.sale_party2.id,
                'description': 'Sale Description',
                'invoice_address': self.sale_party2.addresses[0].id,
                'shipment_address': self.sale_party2.addresses[0].id,
                'carrier': self.carrier.id,
                'lines': [sale_line],
            })
            sale.save()

            self.Sale.quote([sale])
            # No export_type_description set on quoting
            self.assertTrue(sale.dhl_de_export_type_description is None)

            self.Sale.confirm([sale])
            self.Sale.process([sale])


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestDHLDEShipment)
    )
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
