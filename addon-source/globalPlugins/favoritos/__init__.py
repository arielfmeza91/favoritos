# -*- coding: utf-8 -*-
# Complemento "favoritos" para NVDA
# Permite guardar enlaces, carpetas y accesos a archivos o programas,
# y acceder a ellos desde un submenú "Favoritos" en el menú Herramientas de NVDA.

import os
import json
import subprocess
import webbrowser

import wx
import gui
import globalPluginHandler
import globalVars
import addonHandler
import ui
import api
import controlTypes
import scriptHandler
from logHandler import log

addonHandler.initTranslation()

DATA_FILENAME = "favoritos.json"

CATEGORY_ENLACES = "enlaces"
CATEGORY_CARPETAS = "carpetas"
CATEGORY_ACCESOS = "accesos"

MAX_MOST_USED = 10

CATEGORY_TITLES = {
	CATEGORY_ENLACES: _("Enlaces"),
	CATEGORY_CARPETAS: _("Carpetas"),
	CATEGORY_ACCESOS: _("Accesos a archivos o programas"),
}


def _getDataFilePath():
	return os.path.join(globalVars.appArgs.configPath, DATA_FILENAME)


def loadData():
	path = _getDataFilePath()
	if os.path.isfile(path):
		try:
			with open(path, "r", encoding="utf-8") as f:
				data = json.load(f)
				for key in (CATEGORY_ENLACES, CATEGORY_CARPETAS, CATEGORY_ACCESOS):
					data.setdefault(key, [])
				return data
		except Exception:
			log.error("favoritos: no se pudo leer %s" % path, exc_info=True)
	return {CATEGORY_ENLACES: [], CATEGORY_CARPETAS: [], CATEGORY_ACCESOS: []}


def saveData(data):
	path = _getDataFilePath()
	try:
		with open(path, "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent="\t")
	except Exception:
		log.error("favoritos: no se pudo guardar %s" % path, exc_info=True)


def getInstalledBrowsers():
	"""Devuelve una lista de (nombre, ruta) de los navegadores conocidos instalados."""
	roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
	roots = [r for r in roots if r]
	known = [
		("Google Chrome", r"Google\Chrome\Application\chrome.exe"),
		("Microsoft Edge", r"Microsoft\Edge\Application\msedge.exe"),
		("Mozilla Firefox", r"Mozilla Firefox\firefox.exe"),
		("Brave", r"BraveSoftware\Brave-Browser\Application\brave.exe"),
		("Opera", r"Opera\launcher.exe"),
		("Opera", r"Programs\Opera\launcher.exe"),
		("Vivaldi", r"Vivaldi\Application\vivaldi.exe"),
	]
	found = []
	seen = set()
	for name, rel in known:
		if name in seen:
			continue
		for root in roots:
			path = os.path.join(root, rel)
			if os.path.isfile(path):
				found.append((name, path))
				seen.add(name)
				break
	return found


class BrowserChooser(object):
	"""Etiqueta y lista desplegable para elegir con qué navegador se abre un enlace.

	El valor guardado es la ruta del ejecutable, o "" para el navegador predeterminado.
	"""

	def __init__(self, dialog, sizer, selected=""):
		self.dialog = dialog
		self.entries = [(_("Navegador predeterminado"), "")]
		self.entries.extend(getInstalledBrowsers())
		if selected and selected not in [path for _name, path in self.entries]:
			self.entries.append((os.path.basename(selected), selected))
		self.label = wx.StaticText(dialog, label=_("Abrir con:"))
		sizer.Add(self.label, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)
		self.choice = wx.Choice(dialog, choices=self._labels())
		sizer.Add(self.choice, flag=wx.ALL | wx.EXPAND, border=10)
		self.setSelected(selected)
		self.previous = self.choice.GetSelection()
		self.choice.Bind(wx.EVT_CHOICE, self.onChoice)

	def _labels(self):
		return [name for name, _path in self.entries] + [_("Otro navegador...")]

	def setSelected(self, path):
		for i, (_name, entryPath) in enumerate(self.entries):
			if entryPath == path:
				self.choice.SetSelection(i)
				return
		self.choice.SetSelection(0)

	def onChoice(self, evt):
		if self.choice.GetSelection() < len(self.entries):
			self.previous = self.choice.GetSelection()
			return
		dlg = wx.FileDialog(
			self.dialog,
			_("Selecciona el programa del navegador"),
			wildcard=_("Programas (*.exe)|*.exe"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
			self.entries.append((os.path.basename(path), path))
			self.choice.Set(self._labels())
			self.choice.SetSelection(len(self.entries) - 1)
		else:
			self.choice.SetSelection(self.previous)
		self.previous = self.choice.GetSelection()
		dlg.Destroy()

	def enable(self, enabled):
		self.label.Enable(enabled)
		self.choice.Enable(enabled)

	def getSelected(self):
		idx = self.choice.GetSelection()
		if idx == wx.NOT_FOUND or idx >= len(self.entries):
			return ""
		return self.entries[idx][1]


class AddFavoriteDialog(wx.Dialog):
	TYPE_LABELS = [
		_("Enlace (sitio web)"),
		_("Carpeta"),
		_("Acceso a archivo o programa"),
	]
	TYPE_KEYS = [CATEGORY_ENLACES, CATEGORY_CARPETAS, CATEGORY_ACCESOS]

	def __init__(self, parent, key=None, name="", value="", browser=""):
		super().__init__(parent, title=_("Añadir a favoritos"))

		mainSizer = wx.BoxSizer(wx.VERTICAL)

		self.typeRadio = wx.RadioBox(
			self,
			label=_("¿Qué deseas añadir?"),
			choices=self.TYPE_LABELS,
			style=wx.RA_SPECIFY_ROWS,
		)
		if key in self.TYPE_KEYS:
			self.typeRadio.SetSelection(self.TYPE_KEYS.index(key))
		self.typeRadio.Bind(wx.EVT_RADIOBOX, self.onTypeChange)
		mainSizer.Add(self.typeRadio, flag=wx.ALL | wx.EXPAND, border=10)

		nameLabel = wx.StaticText(self, label=_("Nombre:"))
		mainSizer.Add(nameLabel, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)
		self.nameCtrl = wx.TextCtrl(self, value=name)
		mainSizer.Add(self.nameCtrl, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=10)

		self.valueLabel = wx.StaticText(self, label=_("URL:"))
		mainSizer.Add(self.valueLabel, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)
		valueSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.valueCtrl = wx.TextCtrl(self, value=value)
		valueSizer.Add(self.valueCtrl, proportion=1, flag=wx.EXPAND)
		self.browseButton = wx.Button(self, label=_("Examinar..."))
		self.browseButton.Bind(wx.EVT_BUTTON, self.onBrowse)
		valueSizer.Add(self.browseButton, flag=wx.LEFT, border=5)
		mainSizer.Add(valueSizer, flag=wx.ALL | wx.EXPAND, border=10)

		self.browserChooser = BrowserChooser(self, mainSizer, browser)

		buttonSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(buttonSizer, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)

		self.SetSizerAndFit(mainSizer)
		self.onTypeChange(None)
		self.nameCtrl.SetFocus()

	def onTypeChange(self, evt):
		idx = self.typeRadio.GetSelection()
		self.browserChooser.enable(idx == 0)
		if idx == 0:
			self.valueLabel.SetLabel(_("URL:"))
			self.browseButton.Enable(False)
		elif idx == 1:
			self.valueLabel.SetLabel(_("Ruta de la carpeta:"))
			self.browseButton.Enable(True)
		else:
			self.valueLabel.SetLabel(_("Ruta del archivo o programa:"))
			self.browseButton.Enable(True)

	def onBrowse(self, evt):
		idx = self.typeRadio.GetSelection()
		if idx == 1:
			dlg = wx.DirDialog(self, _("Selecciona una carpeta"))
		else:
			dlg = wx.FileDialog(self, _("Selecciona un archivo o programa"))
		if dlg.ShowModal() == wx.ID_OK:
			self.valueCtrl.SetValue(dlg.GetPath())
		dlg.Destroy()

	def onOk(self, evt):
		name = self.nameCtrl.GetValue().strip()
		value = self.valueCtrl.GetValue().strip()
		if not name or not value:
			gui.messageBox(
				_("Debes indicar un nombre y una ruta o URL."),
				_("Favoritos"),
				wx.OK | wx.ICON_WARNING,
				self,
			)
			return
		evt.Skip()

	def getResult(self):
		idx = self.typeRadio.GetSelection()
		key = self.TYPE_KEYS[idx]
		name = self.nameCtrl.GetValue().strip()
		value = self.valueCtrl.GetValue().strip()
		browser = self.browserChooser.getSelected() if key == CATEGORY_ENLACES else ""
		return key, name, value, browser


VALUE_LABELS = {
	CATEGORY_ENLACES: _("URL:"),
	CATEGORY_CARPETAS: _("Ruta de la carpeta:"),
	CATEGORY_ACCESOS: _("Ruta del archivo o programa:"),
}


class EditFavoriteDialog(wx.Dialog):
	def __init__(self, parent, key, name, value, browser=""):
		super().__init__(parent, title=_("Editar favorito"))
		self.key = key

		mainSizer = wx.BoxSizer(wx.VERTICAL)

		nameLabel = wx.StaticText(self, label=_("Nombre:"))
		mainSizer.Add(nameLabel, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)
		self.nameCtrl = wx.TextCtrl(self, value=name)
		mainSizer.Add(self.nameCtrl, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=10)

		valueLabel = wx.StaticText(self, label=VALUE_LABELS[key])
		mainSizer.Add(valueLabel, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)
		valueSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.valueCtrl = wx.TextCtrl(self, value=value)
		valueSizer.Add(self.valueCtrl, proportion=1, flag=wx.EXPAND)
		if key != CATEGORY_ENLACES:
			browseButton = wx.Button(self, label=_("Examinar..."))
			browseButton.Bind(wx.EVT_BUTTON, self.onBrowse)
			valueSizer.Add(browseButton, flag=wx.LEFT, border=5)
		mainSizer.Add(valueSizer, flag=wx.ALL | wx.EXPAND, border=10)

		self.browserChooser = None
		if key == CATEGORY_ENLACES:
			self.browserChooser = BrowserChooser(self, mainSizer, browser)

		buttonSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(buttonSizer, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)

		self.SetSizerAndFit(mainSizer)
		self.nameCtrl.SetFocus()

	def onBrowse(self, evt):
		if self.key == CATEGORY_CARPETAS:
			dlg = wx.DirDialog(self, _("Selecciona una carpeta"))
		else:
			dlg = wx.FileDialog(self, _("Selecciona un archivo o programa"))
		if dlg.ShowModal() == wx.ID_OK:
			self.valueCtrl.SetValue(dlg.GetPath())
		dlg.Destroy()

	def onOk(self, evt):
		name = self.nameCtrl.GetValue().strip()
		value = self.valueCtrl.GetValue().strip()
		if not name or not value:
			gui.messageBox(
				_("Debes indicar un nombre y una ruta o URL."),
				_("Favoritos"),
				wx.OK | wx.ICON_WARNING,
				self,
			)
			return
		evt.Skip()

	def getResult(self):
		browser = self.browserChooser.getSelected() if self.browserChooser else ""
		return self.nameCtrl.GetValue().strip(), self.valueCtrl.GetValue().strip(), browser


class ManageFavoritesDialog(wx.Dialog):
	TYPE_LABELS = AddFavoriteDialog.TYPE_LABELS
	TYPE_KEYS = AddFavoriteDialog.TYPE_KEYS

	def __init__(self, parent):
		super().__init__(parent, title=_("Editar o eliminar favoritos"))
		self.data = loadData()
		self.changed = False

		mainSizer = wx.BoxSizer(wx.VERTICAL)

		self.typeRadio = wx.RadioBox(
			self,
			label=_("Categoría:"),
			choices=self.TYPE_LABELS,
			style=wx.RA_SPECIFY_ROWS,
		)
		self.typeRadio.Bind(wx.EVT_RADIOBOX, self.onTypeChange)
		mainSizer.Add(self.typeRadio, flag=wx.ALL | wx.EXPAND, border=10)

		self.listBox = wx.ListBox(self, style=wx.LB_SINGLE)
		mainSizer.Add(self.listBox, proportion=1, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=10)

		actionSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.editButton = wx.Button(self, label=_("Editar..."))
		self.editButton.Bind(wx.EVT_BUTTON, self.onEdit)
		actionSizer.Add(self.editButton, flag=wx.RIGHT, border=5)
		self.deleteButton = wx.Button(self, label=_("Eliminar"))
		self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
		actionSizer.Add(self.deleteButton)
		mainSizer.Add(actionSizer, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

		closeButton = wx.Button(self, id=wx.ID_CLOSE, label=_("Cerrar"))
		closeButton.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CLOSE))
		closeButton.SetDefault()
		mainSizer.Add(closeButton, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

		self.SetSizerAndFit(mainSizer)
		self.reloadList()
		self.listBox.SetFocus()

	def getCurrentKey(self):
		return self.TYPE_KEYS[self.typeRadio.GetSelection()]

	def onTypeChange(self, evt):
		self.reloadList()

	def reloadList(self):
		items = self.data.get(self.getCurrentKey(), [])
		self.listBox.Set([fav.get("nombre", "") for fav in items])
		hasItems = bool(items)
		self.editButton.Enable(hasItems)
		self.deleteButton.Enable(hasItems)
		if hasItems:
			self.listBox.SetSelection(0)

	def onEdit(self, evt):
		key = self.getCurrentKey()
		idx = self.listBox.GetSelection()
		if idx == wx.NOT_FOUND:
			return
		fav = self.data[key][idx]
		dlg = EditFavoriteDialog(
			self, key, fav.get("nombre", ""), fav.get("valor", ""), fav.get("navegador", "")
		)
		if dlg.ShowModal() == wx.ID_OK:
			name, value, browser = dlg.getResult()
			fav["nombre"] = name
			fav["valor"] = value
			if browser:
				fav["navegador"] = browser
			else:
				fav.pop("navegador", None)
			saveData(self.data)
			self.changed = True
			ui.message(_("Favorito actualizado"))
			self.reloadList()
		dlg.Destroy()

	def onDelete(self, evt):
		key = self.getCurrentKey()
		idx = self.listBox.GetSelection()
		if idx == wx.NOT_FOUND:
			return
		name = self.data[key][idx].get("nombre", "")
		del self.data[key][idx]
		saveData(self.data)
		self.changed = True
		ui.message(_("%s eliminado") % name)
		self.reloadList()


BROWSER_APPS = ("chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "iexplore")


def _looksLikeUrl(text):
	return bool(text) and " " not in text and ("://" in text or "." in text)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	scriptCategory = _("Favoritos")

	def __init__(self):
		super().__init__()
		self.frame = gui.mainFrame
		# El menú de Herramientas se muestra mediante sysTrayIcon.PopupMenu(),
		# así que es sysTrayIcon (y no mainFrame) quien recibe EVT_MENU y
		# EVT_MENU_OPEN de sus elementos. Vincular a mainFrame deja los
		# manejadores sin efecto: el menú se ve bien, pero nada responde.
		self.sysTrayIcon = gui.mainFrame.sysTrayIcon
		self.toolsMenu = self.sysTrayIcon.toolsMenu

		self.favoritosMenu = wx.Menu()

		addItem = self.favoritosMenu.Append(wx.ID_ANY, _("Añadir a favoritos..."))
		self.sysTrayIcon.Bind(wx.EVT_MENU, self.onAdd, addItem)

		manageItem = self.favoritosMenu.Append(wx.ID_ANY, _("Editar o eliminar favoritos..."))
		self.sysTrayIcon.Bind(wx.EVT_MENU, self.onManage, manageItem)

		self.favoritosMenu.AppendSeparator()

		self.mostUsedMenu = wx.Menu()
		self.favoritosMenu.AppendSubMenu(self.mostUsedMenu, _("Más usados"))

		self.categoryMenus = {}
		for key in (CATEGORY_ENLACES, CATEGORY_CARPETAS, CATEGORY_ACCESOS):
			submenu = wx.Menu()
			self.favoritosMenu.AppendSubMenu(submenu, CATEGORY_TITLES[key])
			self.categoryMenus[key] = submenu

		self.favoritosMenu.AppendSeparator()

		helpItem = self.favoritosMenu.Append(wx.ID_ANY, _("Ayuda"))
		self.sysTrayIcon.Bind(wx.EVT_MENU, self.onHelp, helpItem)

		self.favoritosMenuItem = self.toolsMenu.AppendSubMenu(self.favoritosMenu, _("Favoritos"))

		# Los submenús de categoría se reconstruyen aquí (con los datos ya
		# guardados) y luego cada vez que se añade o elimina un favorito.
		# NVDA no usa EVT_MENU_OPEN para refrescar contenido dinámico en sus
		# propios menús (los construye una sola vez), y en la práctica ese
		# evento no llega de forma fiable a submenús anidados varios niveles
		# dentro de un menú emergente; por eso el contenido se mantiene
		# sincronizado en el momento en que cambian los datos, no al abrir.
		self._refreshCategoryMenus()

		log.info("favoritos: complemento inicializado. addItem id=%r helpItem id=%r" % (addItem.GetId(), helpItem.GetId()))

	def terminate(self):
		try:
			self.toolsMenu.Remove(self.favoritosMenuItem)
		except Exception:
			log.error("favoritos: error al terminar el complemento", exc_info=True)
		super().terminate()

	def _refreshCategoryMenus(self):
		data = loadData()
		for key, submenu in self.categoryMenus.items():
			self._rebuildCategoryMenu(key, submenu, data)
		self._rebuildMostUsedMenu(data)

	def _clearMenu(self, menu):
		for item in list(menu.GetMenuItems()):
			try:
				self.sysTrayIcon.Unbind(wx.EVT_MENU, id=item.GetId())
			except Exception:
				pass
			menu.DestroyItem(item)

	def _populateMenu(self, menu, entries):
		"""Rellena un menú con entradas (categoría, favorito, etiqueta)."""
		self._clearMenu(menu)
		if not entries:
			emptyItem = menu.Append(wx.ID_ANY, _("(No hay elementos)"))
			emptyItem.Enable(False)
			return
		for key, fav, label in entries:
			item = menu.Append(wx.ID_ANY, label)
			self.sysTrayIcon.Bind(
				wx.EVT_MENU,
				lambda evt, k=key, f=fav: self._openFavorite(k, f),
				id=item.GetId(),
			)

	def _rebuildCategoryMenu(self, key, menu, data=None):
		if data is None:
			data = loadData()
		items = data.get(key, [])
		log.info("favoritos: _rebuildCategoryMenu key=%r -> %d elementos" % (key, len(items)))
		self._populateMenu(menu, [(key, fav, fav.get("nombre", "")) for fav in items])

	def _rebuildMostUsedMenu(self, data=None):
		if data is None:
			data = loadData()
		used = [
			(key, fav)
			for key in (CATEGORY_ENLACES, CATEGORY_CARPETAS, CATEGORY_ACCESOS)
			for fav in data.get(key, [])
			if fav.get("usos", 0) > 0
		]
		used.sort(key=lambda entry: entry[1].get("usos", 0), reverse=True)
		entries = [
			(key, fav, "%s (%s)" % (fav.get("nombre", ""), CATEGORY_TITLES[key]))
			for key, fav in used[:MAX_MOST_USED]
		]
		self._populateMenu(self.mostUsedMenu, entries)

	def _openFavorite(self, key, fav):
		if key == CATEGORY_ENLACES:
			opened = self.openLink(fav.get("valor", ""), fav.get("navegador", ""))
		else:
			opened = self.openPath(fav.get("valor", ""))
		if opened:
			self._registerUse(key, fav)
			# Se difiere: los menús no deben destruirse mientras se procesa
			# el evento de uno de sus propios elementos.
			wx.CallAfter(self._refreshCategoryMenus)

	def _registerUse(self, key, fav):
		data = loadData()
		for stored in data.get(key, []):
			if stored.get("nombre") == fav.get("nombre") and stored.get("valor") == fav.get("valor"):
				stored["usos"] = stored.get("usos", 0) + 1
				saveData(data)
				return

	def onAdd(self, evt):
		log.info("favoritos: onAdd recibido (evt id=%r)" % evt.GetId())
		# Se difiere con wx.CallAfter porque el menú de Herramientas todavía
		# se está cerrando en este punto; mostrar el diálogo modal aquí
		# directamente hace que Windows lo cree sin foco ni pintarlo.
		wx.CallAfter(self._showAddDialog)
		log.info("favoritos: onAdd -> wx.CallAfter encolado")

	def _showAddDialog(self, key=None, name="", value="", browser=""):
		log.info("favoritos: _showAddDialog iniciando")
		try:
			dlg = AddFavoriteDialog(self.frame, key, name, value, browser)
			log.info("favoritos: diálogo creado, llamando a ShowModal")
			result = dlg.ShowModal()
			log.info("favoritos: ShowModal devolvió %r (wx.ID_OK=%r)" % (result, wx.ID_OK))
			if result == wx.ID_OK:
				key, name, value, browser = dlg.getResult()
				data = loadData()
				fav = {"nombre": name, "valor": value}
				if browser:
					fav["navegador"] = browser
				data.setdefault(key, []).append(fav)
				saveData(data)
				self._rebuildCategoryMenu(key, self.categoryMenus[key])
				ui.message(_("%s añadido a %s") % (name, CATEGORY_TITLES[key]))
				log.info("favoritos: guardado '%s' en %s" % (name, key))
			dlg.Destroy()
		except Exception:
			log.error("favoritos: excepción en _showAddDialog", exc_info=True)
			raise

	def _getCurrentPage(self):
		"""Devuelve (título, url) de la página del navegador activo, o None."""
		obj = api.getFocusObject()
		treeInterceptor = getattr(obj, "treeInterceptor", None)
		if treeInterceptor is not None:
			url = getattr(treeInterceptor, "documentConstantIdentifier", None)
			if isinstance(url, str) and "://" in url:
				title = getattr(treeInterceptor.rootNVDAObject, "name", "") or ""
				return title.strip() or url, url
		# Respaldo: el foco está en la barra de direcciones de un navegador.
		appName = (getattr(getattr(obj, "appModule", None), "appName", "") or "").lower()
		# NVDA 2021.2+ usa controlTypes.Role; las versiones anteriores, ROLE_*.
		roles = getattr(controlTypes, "Role", None)
		editableRole = roles.EDITABLETEXT if roles else controlTypes.ROLE_EDITABLETEXT
		if appName in BROWSER_APPS and obj.role == editableRole:
			value = (obj.value or "").strip()
			if _looksLikeUrl(value):
				if "://" not in value:
					value = "https://" + value
				title = (api.getForegroundObject().name or "").strip()
				return title or value, value
		return None

	@scriptHandler.script(
		# Translators: descripción del gesto que añade la página actual a favoritos.
		description=_("Añade la página web actual a favoritos"),
		gesture="kb:NVDA+shift+f",
	)
	def script_addCurrentPage(self, gesture):
		page = self._getCurrentPage()
		if page is None:
			ui.message(_("No se pudo detectar la página web actual. Usa este comando desde un navegador."))
			return
		title, url = page
		wx.CallAfter(self._showAddDialog, CATEGORY_ENLACES, title, url)

	def onHelp(self, evt):
		addon = addonHandler.getCodeAddon()
		path = addon.getDocFilePath()
		if path:
			os.startfile(path)
		else:
			gui.messageBox(
				_("No se encontró el archivo de ayuda."),
				_("Favoritos"),
				wx.OK | wx.ICON_ERROR,
				self.frame,
			)

	def onManage(self, evt):
		# Igual que onAdd: se difiere con wx.CallAfter porque el menú de
		# Herramientas todavía se está cerrando en este punto.
		wx.CallAfter(self._showManageDialog)

	def _showManageDialog(self):
		dlg = ManageFavoritesDialog(self.frame)
		try:
			dlg.ShowModal()
		finally:
			if dlg.changed:
				self._refreshCategoryMenus()
			dlg.Destroy()

	def openLink(self, url, browser=""):
		try:
			if browser and os.path.isfile(browser):
				subprocess.Popen([browser, url])
			else:
				if browser:
					ui.message(_("No se encontró el navegador elegido. Se usará el predeterminado."))
				webbrowser.open(url)
			return True
		except Exception:
			log.error("favoritos: no se pudo abrir el enlace %s" % url, exc_info=True)
			gui.messageBox(
				_("No se pudo abrir el enlace."),
				_("Favoritos"),
				wx.OK | wx.ICON_ERROR,
				self.frame,
			)
			return False

	def openPath(self, path):
		try:
			os.startfile(path)
			return True
		except Exception:
			log.error("favoritos: no se pudo abrir la ruta %s" % path, exc_info=True)
			gui.messageBox(
				_("No se pudo abrir el elemento. Es posible que ya no exista."),
				_("Favoritos"),
				wx.OK | wx.ICON_ERROR,
				self.frame,
			)
			return False
