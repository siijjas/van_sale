"""PDF download for the PWA.

Frappe's own ``download_pdf`` leaves the print stylesheet as a ``<link>`` that
wkhtmltopdf then fetches from the site's public URL. On servers that sit behind a
proxy / CDN that fetch can come back 404 (a cached miss, a hostname that resolves to
another vhost, a stale asset hash) and wkhtmltopdf aborts the whole PDF with
``ContentNotFoundError`` even though the HTML itself rendered fine. A missing image
only drops the image, but a missing stylesheet kills the PDF.

So this endpoint renders the same HTML, inlines the print stylesheet from disk, and
tells wkhtmltopdf to ignore media it cannot load. The PDF then never depends on the
server being able to reach itself over the network.
"""

import os
import re

import frappe
from frappe.utils import cint
from frappe.utils.pdf import get_pdf
from frappe.www.printview import validate_print_permission

from van_sale.van_sale.utils import _is_manager

SHIFT_DOCTYPES = ("Van Shift Opening", "Van Shift Closing")

_STYLESHEET_LINK = re.compile(r'<link[^>]+href="(?P<href>[^"]*/assets/[^"]+\.css)"[^>]*>', re.IGNORECASE)


def _inline_stylesheets(html: str) -> str:
	"""Replace ``<link href="/assets/....css">`` tags with the file's contents."""

	def replace(match: re.Match) -> str:
		href = match.group("href").split("?", 1)[0]
		rel = href.split("/assets/", 1)[1]
		path = os.path.join(frappe.local.sites_path, "assets", rel)
		if not os.path.isfile(path):
			return match.group(0)
		with open(path, encoding="utf-8") as f:
			css = f.read()
		# Relative url(...) references (fonts) would otherwise resolve against the page.
		base = "/assets/" + rel.rsplit("/", 1)[0] + "/"
		css = re.sub(r"url\((['\"]?)(?!data:|https?:|/)", lambda m: f"url({m.group(1)}{base}", css)
		return f"<style>{css}</style>"

	return _STYLESHEET_LINK.sub(replace, html)


@frappe.whitelist()
def download_pdf(doctype: str, name: str, format: str | None = None, no_letterhead: int = 0):
	"""Drop-in for ``frappe.utils.print_format.download_pdf`` (same query parameters)."""
	doc = frappe.get_doc(doctype, name)
	validate_print_permission(doc)
	# Drivers hold a plain read/print DocPerm on shift documents; the app limits them
	# to their own shifts (managers see everyone's), same as the report endpoints.
	if doctype in SHIFT_DOCTYPES and not _is_manager() and doc.driver != frappe.session.user:
		frappe.throw(frappe._("You can only print your own shift reports."), frappe.PermissionError)

	html = frappe.get_print(doctype, name, format, doc=doc, no_letterhead=cint(no_letterhead))
	html = _inline_stylesheets(html)
	pdf = get_pdf(html, options={"load-media-error-handling": "ignore"})

	frappe.local.response.filename = "{}.pdf".format(name.replace(" ", "-").replace("/", "-"))
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"
