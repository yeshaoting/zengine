# -*-  coding: utf-8 -*-
# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
"""
This module consists view methods of add/edit catalog datas of framework.
"""
__author__ = 'evren kutar'

from pyoko.db.connection import client
from pyoko import Model, field, ListNode
from zengine.views.crud import CrudView, form_modifier
from zengine import forms
from zengine.forms import fields
from falcon import HTTPBadRequest


class CatalogSelectForm(forms.JsonForm):
    """
    Generates Form object for catalog select view.
    """
    class Meta:
        title = 'Choose Catalog Data'
        help_text = "Type and choose existing catalog data to edit. Or if you want to add one type the name of the catalog data you want to add."

    # typeahead type added for forms todo: add to documentation
    catalog = fields.Integer("Catalogs", type='typeahead')
    edit = fields.Button("Edit", cmd="get_catalog")


class CatalogEditForm(forms.JsonForm):
    """
    Generates Form object with ListNode to add and edit catalog data
    ListNode used for inline edit items on ui.
    """
    save = fields.Button("Save", cmd="save_catalog", flow="start")
    cancel = fields.Button("Cancel", cmd="cancel", flow="start")

    class CatalogDatas(ListNode):
        catalog_key = fields.String("")
        tr = fields.String("Türkçe")
        en = fields.String("English")


fixture_bucket = client.bucket_type('catalog').bucket('ulakbus_settings_fixtures')


class CatalogDataView(CrudView):
    """
    Workflow class of catalog add/edit screens
    """
    class Meta:
        model = 'User'

    def list_catalogs(self):
        """
        Lists existing catalogs respect to ui view template format
        """
        self.fixtures = [{"value": i, "name": i} for i in fixture_bucket.get_keys()]
        self.form_out(CatalogSelectForm(current=self.current))

    def get_catalog(self):
        """
        Get existing catalog and fill the form with the model data.
        If given key not found as catalog, it generates an empty catalog data form.
        """

        catalog_data = fixture_bucket.get(self.input['form']['catalog'])

        # define add or edit based on catalog data exists
        add_or_edit = "Edit" if catalog_data.exists else "Add"

        # generate form
        catalog_edit_form = CatalogEditForm(
            current=self.current,
            title='%s: %s' % (add_or_edit, self.input['form']['catalog']))

        # add model data to form
        if catalog_data.exists:
            if type(catalog_data.data) == list:
                # if catalog data is an array it means no other language of value defined, therefor the value is turkish
                for key, data in enumerate(catalog_data.data):
                    catalog_edit_form.CatalogDatas(catalog_key=key or "0", en='', tr=data)
            if type(catalog_data.data) == dict:
                for key, data in catalog_data.data.items():
                    catalog_edit_form.CatalogDatas(catalog_key=key, en=data['en'], tr=data['tr'])

        else:
            catalog_edit_form.CatalogDatas(catalog_key="0", en='', tr='')

        self.form_out(catalog_edit_form)
        # we do NOT want checkboxes on right of the ui table view
        self.output["meta"]["allow_selection"] = False

        # set meta translate_widget to True to use translate view for ui
        # todo: add to documentation / longterm: add to zengine-ui
        self.output["meta"]["translate_widget"] = True

        # schema key for get back what key will be saved, used in save_catalog form
        self.output["object_key"] = self.input['form']['catalog']

    def save_catalog(self):
        """
        Saves the catalog data to given key
        Cancels if the cmd is cancel
        Notifies user with the process.
        """
        if self.input["cmd"] == 'save_catalog':
            try:
                edited_object = dict()
                for i in self.input["form"]["CatalogDatas"]:
                    edited_object[i["catalog_key"]] = {"en": i["en"], "tr": i["tr"]}

                newobj = fixture_bucket.get(self.input["object_key"])
                newobj.data = edited_object
                newobj.store()

                # notify user by passing notify in output object
                # todo: add ui-api document the feature notify
                self.output["notify"] = "catalog: %s successfully updated." % self.input["object_key"]
            except:
                raise HTTPBadRequest("Form object could not be saved")
        if self.input["cmd"] == 'cancel':
            self.output["notify"] = "catalog: %s canceled." % self.input["object_key"]

    @form_modifier
    def change_form_elements(self, serialized_form):
        """
        This function edits form elements as can be understood from the name of its decorator
        :param serialized_form:
        """
        if 'catalog' in serialized_form['schema']['properties']:
            serialized_form['schema']['properties']['catalog']['titleMap'] = self.fixtures
        if 'CatalogDatas' in serialized_form['schema']['properties']:
            serialized_form['inline_edit'] = ['catalog_key', 'tr', 'en']
