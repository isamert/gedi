import os
import tempfile
import subprocess

from jedi.api import Script
from gi.repository import GObject, Gedit, Gtk, GtkSource

#FIXME: find real icon names
icon_names = {'import': '',
              'module': '',
              'class': '',
              'function': '',
              'statement': '',
              'param': ''}

class Jedi:
    def get_script(document):
        doc_text = document.get_text(document.get_start_iter(), document.get_end_iter(), False)
        iter_cursor = document.get_iter_at_mark(document.get_insert())
        linenum = iter_cursor.get_line() + 1
        charnum = iter_cursor.get_line_index()

        return Script(doc_text, linenum, charnum, document.get_uri_for_display())


class GediPlugin(GObject.Object, Gedit.ViewActivatable):
    __gtype_name__ = "GediPlugin"
    py_extension = ".py"
    view = GObject.property(type=Gedit.View)

    def __init__(self):
        GObject.Object.__init__(self)
        self.completion_provider = None

    def do_activate(self):
        print("Gedi is activated.")
        document = self.view.get_buffer()
        document.connect("load", self.on_document_load)

        if document.get_uri_for_display().endswith(self.py_extension):
            self.completion_provider = GediCompletionProvider()
            self.view.get_completion().add_provider(self.completion_provider)

    def do_deactivate(self):
        print("Gedi is deactivated.")

    def on_document_load(self, document):
        if document.get_uri_for_display().endswith(self.py_extension):
            if self.completion_provider is None:
                self.completion_provider = GediCompletionProvider()
                self.view.get_completion().add_provider(self.completion_provider)
        else:
            if self.completion_provider is not None:
                self.view.get_completion().remove_provider(self.completion_provider)
                self.completion_provider = None


class GediCompletionProvider(GObject.Object, GtkSource.CompletionProvider):
    __gtype_name__ = 'GediProvider'

    def __init__(self):
        GObject.Object.__init__(self)

    def do_get_name(self):
        return _("Gedi Python Code Completion")
    
    def get_iter_correctly(self, context):
        if isinstance(context.get_iter(), tuple):
            return context.get_iter()[1];
        else:
            return context.get_iter()

    def do_match(self, context):
        #FIXME: check for strings and comments
        iter = self.get_iter_correctly(context)
        iter.backward_char()
        ch = iter.get_char()
        if not (ch in ('_', '.') or ch.isalnum()):
            return False

        return True

    def do_get_priority(self):
        return 1

    def do_get_activation(self):
        return GtkSource.CompletionActivation.INTERACTIVE

    def do_populate(self, context):
        #TODO: do async maybe?
        it = self.get_iter_correctly(context)
        document = it.get_buffer()
        proposals = []
        
        for completion in Jedi.get_script(document).completions():
            complete = completion.name
            if jedi.__version__ <= (0,7,0):
                doc=completion.doc
            else:
                doc=completion.docstring()
            proposals.append(GtkSource.CompletionItem.new(completion.name,
                                                            completion.name,
                                                            self.get_icon_for_type(completion.type),
                                                            doc))


        context.add_proposals(self, proposals, True)

    def get_icon_for_type(self, _type):
        theme = Gtk.IconTheme.get_default()
        try:
            return theme.load_icon(icon_names[_type.lower()], 16, 0)
        except:
            try:
                return theme.load_icon(Gtk.STOCK_ADD, 16, 0)
            except:
                return None


GObject.type_register(GediCompletionProvider)
