# Generated by Django 5.1.7 on 2025-03-24 12:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0007_remove_signatory_user_signatory_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='signatoryapproval',
            name='email',
            field=models.EmailField(max_length=254),
        ),
    ]
