# Generated by Django 4.0.5 on 2022-06-04 18:55

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_invitation'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='time_created',
            field=models.DateTimeField(auto_created=True, default=datetime.datetime(2022, 6, 4, 18, 55, 51, 51736, tzinfo=utc)),
            preserve_default=False,
        ),
    ]