# Generated by Django 4.0.5 on 2022-06-07 15:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_invitation_administrator'),
    ]

    operations = [
        migrations.AddField(
            model_name='twitchintegration',
            name='delay_subscriber',
            field=models.FloatField(default=15),
        ),
    ]
