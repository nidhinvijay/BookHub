# Generated by Django 5.1.5 on 2025-06-24 10:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0002_book_librarian_name_borrowing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='borrowing',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_transactions', to='app.librarian'),
        ),
        migrations.AlterField(
            model_name='borrowing',
            name='book',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='app.book'),
        ),
        migrations.AlterField(
            model_name='borrowing',
            name='member',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='app.member'),
        ),
        migrations.AlterField(
            model_name='borrowing',
            name='status',
            field=models.CharField(choices=[('pending_purchase', 'Pending Purchase Approval'), ('purchased', 'Purchased'), ('rejected_purchase', 'Rejected Purchase')], default='pending_purchase', max_length=20),
        ),
    ]
