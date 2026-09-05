# Generated migration for generic payment method labels

from django.db import migrations, models


def migrate_payment_methods_forward(apps, schema_editor):
    """Map old payment method identifiers to generic labels."""
    Expense = apps.get_model('spend', 'Expense')
    
    mapping = {
        'amex_1009': 'card_a',
        'visa_5540': 'card_b',
        'amex_8515': 'card_c',
        'paypal_cap1': 'paypal_bank',
        'stripe_link': 'stripe_link',
        'paypal': 'paypal',
        'other': 'other',
    }
    
    for old_key, new_key in mapping.items():
        Expense.objects.filter(payment_method=old_key).update(payment_method=new_key)


def migrate_payment_methods_reverse(apps, schema_editor):
    """Reverse mapping from generic labels to old identifiers."""
    Expense = apps.get_model('spend', 'Expense')
    
    reverse_mapping = {
        'card_a': 'amex_1009',
        'card_b': 'visa_5540',
        'card_c': 'amex_8515',
        'paypal_bank': 'paypal_cap1',
        'stripe_link': 'stripe_link',
        'paypal': 'paypal',
        'other': 'other',
    }
    
    for new_key, old_key in reverse_mapping.items():
        Expense.objects.filter(payment_method=new_key).update(payment_method=old_key)


class Migration(migrations.Migration):

    dependencies = [
        ('spend', '0003_add_expense_model_and_subscription_providers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expense',
            name='payment_method',
            field=models.CharField(
                choices=[
                    ('card_a', 'Card A'),
                    ('card_b', 'Card B'),
                    ('card_c', 'Card C'),
                    ('stripe_link', 'Link (Stripe)'),
                    ('paypal_bank', 'PayPal (bank)'),
                    ('paypal', 'PayPal'),
                    ('other', 'Other'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(
            migrate_payment_methods_forward,
            migrate_payment_methods_reverse,
        ),
    ]
