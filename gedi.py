#!/usr/bin/env python3

import os, jedi, threading
from gi.repository import Gtk, GLib, Gedit, GObject, GtkSource

jedi.settings.fast_parser = False  # activate thread-safety

# FIXME: find real icon names
ICON_NAMES = {
	'import': '',
	'module': '',
	'class': '',
	'function': '',
	'statement': '',
	'param': '',
}

class GediPlugin(GObject.Object, Gedit.ViewActivatable):
	__gtype_name__ = 'GediPlugin'

	view = GObject.property(type=Gedit.View)

	def __init__(self):
		super().__init__()
		self.completion_provider = None
		self.signal = None

	def do_activate(self):
		document = self.view.get_buffer()
		self.signal = document.connect('loaded', self.on_document_load)
		self.on_document_load(document)

	def do_deactivate(self):
		if (self.signal is not None):
			document = self.view.get_buffer()
			document.disconnect(self.signal)

	def on_document_load(self, document, *_):
		if ((lang := document.get_language()) and 'python' in lang.get_name().casefold()):
			self.completion_provider = GediCompletionProvider(document)
			self.view.get_completion().add_provider(self.completion_provider)
		else:
			if (self.completion_provider is not None):
				self.view.get_completion().remove_provider(self.completion_provider)
				self.completion_provider = None

@GObject.type_register
class GediCompletionProvider(GObject.Object, GtkSource.CompletionProvider):
	__gtype_name__ = 'GediProvider'

	icon_theme = Gtk.IconTheme.get_default()

	def __init__(self, document):
		super().__init__()
		self.document = document
		self.populate_thread_ident = None
		self.populate_thread_lock = threading.Lock()

	def do_get_name(self):
		return _("Gedi Python Code Completion")

	def do_match(self, context):
		iter = context.get_iter()[1]
		iter.backward_char()
		if ('no-spell-check' not in self.document.get_context_classes_at_iter(iter)): return False
		ch = iter.get_char()
		return (ch in '_.' or ch.isalnum())

	def do_get_priority(self):
		return 1

	def do_get_activation(self):
		return GtkSource.CompletionActivation.INTERACTIVE

	def do_populate(self, context):
		code = self.document.get_text(self.document.get_start_iter(), self.document.get_end_iter(), False)
		path = (loc.get_path() if (loc := self.document.get_file().get_location()) else '')
		iter_cursor = self.document.get_iter_at_mark(self.document.get_insert())
		linenum = iter_cursor.get_line()+1
		charnum = iter_cursor.get_line_index()

		(t := threading.Thread(target=self.populate, args=(context, code, path, linenum, charnum))).start()
		with self.populate_thread_lock:
			self.populate_thread_ident = t.ident

	def populate(self, context, code, path, linenum, charnum):
		script = jedi.Script(code=code, path=path, environment=jedi.api.environment.InterpreterEnvironment())
		completions = script.complete(linenum, charnum, fuzzy=False)

		proposals = [GtkSource.CompletionItem(
		             	label = i.name,
		             	text = i.name,
		             	icon = self.icon_theme.load_icon(ICON_NAMES.get(i.type.lower()) or Gtk.STOCK_ADD, 16, 0),
		             	info = i.docstring(),
		             ) for i in completions]

		ident = threading.get_ident()
		with self.populate_thread_lock:
			if (ident != self.populate_thread_ident): return

		GLib.idle_add(context.add_proposals, self, proposals, True)
