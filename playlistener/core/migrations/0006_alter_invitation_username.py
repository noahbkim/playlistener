# Generated by Django 4.0.5 on 2022-06-04 18:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_alter_discordintegration_time_created_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invitation',
            name='username',
            field=models.CharField(max_length=150, unique=True),
        ),
    ]
