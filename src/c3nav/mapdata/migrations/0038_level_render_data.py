# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-10-20 19:43
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mapdata', '0037_level_geoms_cache'),
    ]

    operations = [
        migrations.RenameField(
            model_name='level',
            old_name='geoms_cache',
            new_name='render_data',
        ),
        migrations.AlterField(
            model_name='level',
            name='render_data',
            field=models.BinaryField(null=True),
        ),
    ]
