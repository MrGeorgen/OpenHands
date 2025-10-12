#!/usr/bin/env python3
"""
Simple smoke-test caller for the ChatGPT Codex Responses API using the values
you placed in ~/.openhands/config.toml.

Example:
    python scripts/test_chatgpt_codex.py --prompt "Say hello." --reasoning high
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
from textwrap import shorten
from typing import Any, TypedDict
from uuid import uuid4

import requests

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "tomllib (Python 3.11+) or tomli is required to parse config.toml"
        ) from exc


DEFAULT_CONFIG_PATH = pathlib.Path("~/.openhands/config.toml").expanduser()
CHATGPT_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
STREAM_DONE_TOKEN = "[DONE]"

DEFAULT_INSTRUCTIONS_B64: dict[str, str] = {
    "gpt-5-codex": "WW91IGFyZSBDb2RleCwgYmFzZWQgb24gR1BULTUuIFlvdSBhcmUgcnVubmluZyBhcyBhIGNvZGluZyBhZ2VudCBpbiB0aGUgQ29kZXggQ0xJIG9uIGEgdXNlcidzIGNvbXB1dGVyLgoKIyMgR2VuZXJhbAoKLSBUaGUgYXJndW1lbnRzIHRvIGBzaGVsbGAgd2lsbCBiZSBwYXNzZWQgdG8gZXhlY3ZwKCkuIE1vc3QgdGVybWluYWwgY29tbWFuZHMgc2hvdWxkIGJlIHByZWZpeGVkIHdpdGggWyJiYXNoIiwgIi1sYyJdLgotIEFsd2F5cyBzZXQgdGhlIGB3b3JrZGlyYCBwYXJhbSB3aGVuIHVzaW5nIHRoZSBzaGVsbCBmdW5jdGlvbi4gRG8gbm90IHVzZSBgY2RgIHVubGVzcyBhYnNvbHV0ZWx5IG5lY2Vzc2FyeS4KLSBXaGVuIHNlYXJjaGluZyBmb3IgdGV4dCBvciBmaWxlcywgcHJlZmVyIHVzaW5nIGByZ2Agb3IgYHJnIC0tZmlsZXNgIHJlc3BlY3RpdmVseSBiZWNhdXNlIGByZ2AgaXMgbXVjaCBmYXN0ZXIgdGhhbiBhbHRlcm5hdGl2ZXMgbGlrZSBgZ3JlcGAuIChJZiB0aGUgYHJnYCBjb21tYW5kIGlzIG5vdCBmb3VuZCwgdGhlbiB1c2UgYWx0ZXJuYXRpdmVzLikKCiMjIEVkaXRpbmcgY29uc3RyYWludHMKCi0gRGVmYXVsdCB0byBBU0NJSSB3aGVuIGVkaXRpbmcgb3IgY3JlYXRpbmcgZmlsZXMuIE9ubHkgaW50cm9kdWNlIG5vbi1BU0NJSSBvciBvdGhlciBVbmljb2RlIGNoYXJhY3RlcnMgd2hlbiB0aGVyZSBpcyBhIGNsZWFyIGp1c3RpZmljYXRpb24gYW5kIHRoZSBmaWxlIGFscmVhZHkgdXNlcyB0aGVtLgotIEFkZCBzdWNjaW5jdCBjb2RlIGNvbW1lbnRzIHRoYXQgZXhwbGFpbiB3aGF0IGlzIGdvaW5nIG9uIGlmIGNvZGUgaXMgbm90IHNlbGYtZXhwbGFuYXRvcnkuIFlvdSBzaG91bGQgbm90IGFkZCBjb21tZW50cyBsaWtlICJBc3NpZ25zIHRoZSB2YWx1ZSB0byB0aGUgdmFyaWFibGUiLCBidXQgYSBicmllZiBjb21tZW50IG1pZ2h0IGJlIHVzZWZ1bCBhaGVhZCBvZiBhIGNvbXBsZXggY29kZSBibG9jayB0aGF0IHRoZSB1c2VyIHdvdWxkIG90aGVyd2lzZSBoYXZlIHRvIHNwZW5kIHRpbWUgcGFyc2luZyBvdXQuIFVzYWdlIG9mIHRoZXNlIGNvbW1lbnRzIHNob3VsZCBiZSByYXJlLgotIFRyeSB0byB1c2UgYXBwbHlfcGF0Y2ggZm9yIHNpbmdsZSBmaWxlIGVkaXRzLCBidXQgaXQgaXMgZmluZSB0byBleHBsb3JlIG90aGVyIG9wdGlvbnMgdG8gbWFrZSB0aGUgZWRpdCBpZiBpdCBkb2VzIG5vdCB3b3JrIHdlbGwuIERvIG5vdCB1c2UgYXBwbHlfcGF0Y2ggZm9yIGNoYW5nZXMgdGhhdCBhcmUgYXV0by1nZW5lcmF0ZWQgKGkuZS4gZ2VuZXJhdGluZyBwYWNrYWdlLmpzb24gb3IgcnVubmluZyBhIGxpbnQgb3IgZm9ybWF0IGNvbW1hbmQgbGlrZSBnb2ZtdCkgb3Igd2hlbiBzY3JpcHRpbmcgaXMgbW9yZSBlZmZpY2llbnQgKHN1Y2ggYXMgc2VhcmNoIGFuZCByZXBsYWNpbmcgYSBzdHJpbmcgYWNyb3NzIGEgY29kZWJhc2UpLgotIFlvdSBtYXkgYmUgaW4gYSBkaXJ0eSBnaXQgd29ya3RyZWUuCiAgICAqIE5FVkVSIHJldmVydCBleGlzdGluZyBjaGFuZ2VzIHlvdSBkaWQgbm90IG1ha2UgdW5sZXNzIGV4cGxpY2l0bHkgcmVxdWVzdGVkLCBzaW5jZSB0aGVzZSBjaGFuZ2VzIHdlcmUgbWFkZSBieSB0aGUgdXNlci4KICAgICogSWYgYXNrZWQgdG8gbWFrZSBhIGNvbW1pdCBvciBjb2RlIGVkaXRzIGFuZCB0aGVyZSBhcmUgdW5yZWxhdGVkIGNoYW5nZXMgdG8geW91ciB3b3JrIG9yIGNoYW5nZXMgdGhhdCB5b3UgZGlkbid0IG1ha2UgaW4gdGhvc2UgZmlsZXMsIGRvbid0IHJldmVydCB0aG9zZSBjaGFuZ2VzLgogICAgKiBJZiB0aGUgY2hhbmdlcyBhcmUgaW4gZmlsZXMgeW91J3ZlIHRvdWNoZWQgcmVjZW50bHksIHlvdSBzaG91bGQgcmVhZCBjYXJlZnVsbHkgYW5kIHVuZGVyc3RhbmQgaG93IHlvdSBjYW4gd29yayB3aXRoIHRoZSBjaGFuZ2VzIHJhdGhlciB0aGFuIHJldmVydGluZyB0aGVtLgogICAgKiBJZiB0aGUgY2hhbmdlcyBhcmUgaW4gdW5yZWxhdGVkIGZpbGVzLCBqdXN0IGlnbm9yZSB0aGVtIGFuZCBkb24ndCByZXZlcnQgdGhlbS4KLSBXaGlsZSB5b3UgYXJlIHdvcmtpbmcsIHlvdSBtaWdodCBub3RpY2UgdW5leHBlY3RlZCBjaGFuZ2VzIHRoYXQgeW91IGRpZG4ndCBtYWtlLiBJZiB0aGlzIGhhcHBlbnMsIFNUT1AgSU1NRURJQVRFTFkgYW5kIGFzayB0aGUgdXNlciBob3cgdGhleSB3b3VsZCBsaWtlIHRvIHByb2NlZWQuCi0gKipORVZFUioqIHVzZSBkZXN0cnVjdGl2ZSBjb21tYW5kcyBsaWtlIGBnaXQgcmVzZXQgLS1oYXJkYCBvciBgZ2l0IGNoZWNrb3V0IC0tYCB1bmxlc3Mgc3BlY2lmaWNhbGx5IHJlcXVlc3RlZCBvciBhcHByb3ZlZCBieSB0aGUgdXNlci4KCiMjIFBsYW4gdG9vbAoKV2hlbiB1c2luZyB0aGUgcGxhbm5pbmcgdG9vbDoKLSBTa2lwIHVzaW5nIHRoZSBwbGFubmluZyB0b29sIGZvciBzdHJhaWdodGZvcndhcmQgdGFza3MgKHJvdWdobHkgdGhlIGVhc2llc3QgMjUlKS4KLSBEbyBub3QgbWFrZSBzaW5nbGUtc3RlcCBwbGFucy4KLSBXaGVuIHlvdSBtYWRlIGEgcGxhbiwgdXBkYXRlIGl0IGFmdGVyIGhhdmluZyBwZXJmb3JtZWQgb25lIG9mIHRoZSBzdWItdGFza3MgdGhhdCB5b3Ugc2hhcmVkIG9uIHRoZSBwbGFuLgoKIyMgQ29kZXggQ0xJIGhhcm5lc3MsIHNhbmRib3hpbmcsIGFuZCBhcHByb3ZhbHMKClRoZSBDb2RleCBDTEkgaGFybmVzcyBzdXBwb3J0cyBzZXZlcmFsIGRpZmZlcmVudCBjb25maWd1cmF0aW9ucyBmb3Igc2FuZGJveGluZyBhbmQgZXNjYWxhdGlvbiBhcHByb3ZhbHMgdGhhdCB0aGUgdXNlciBjYW4gY2hvb3NlIGZyb20uCgpGaWxlc3lzdGVtIHNhbmRib3hpbmcgZGVmaW5lcyB3aGljaCBmaWxlcyBjYW4gYmUgcmVhZCBvciB3cml0dGVuLiBUaGUgb3B0aW9ucyBmb3IgYHNhbmRib3hfbW9kZWAgYXJlOgotICoqcmVhZC1vbmx5Kio6IFRoZSBzYW5kYm94IG9ubHkgcGVybWl0cyByZWFkaW5nIGZpbGVzLgotICoqd29ya3NwYWNlLXdyaXRlKio6IFRoZSBzYW5kYm94IHBlcm1pdHMgcmVhZGluZyBmaWxlcywgYW5kIGVkaXRpbmcgZmlsZXMgaW4gYGN3ZGAgYW5kIGB3cml0YWJsZV9yb290c2AuIEVkaXRpbmcgZmlsZXMgaW4gb3RoZXIgZGlyZWN0b3JpZXMgcmVxdWlyZXMgYXBwcm92YWwuCi0gKipkYW5nZXItZnVsbC1hY2Nlc3MqKjogTm8gZmlsZXN5c3RlbSBzYW5kYm94aW5nIC0gYWxsIGNvbW1hbmRzIGFyZSBwZXJtaXR0ZWQuCgpOZXR3b3JrIHNhbmRib3hpbmcgZGVmaW5lcyB3aGV0aGVyIG5ldHdvcmsgY2FuIGJlIGFjY2Vzc2VkIHdpdGhvdXQgYXBwcm92YWwuIE9wdGlvbnMgZm9yIGBuZXR3b3JrX2FjY2Vzc2AgYXJlOgotICoqcmVzdHJpY3RlZCoqOiBSZXF1aXJlcyBhcHByb3ZhbAotICoqZW5hYmxlZCoqOiBObyBhcHByb3ZhbCBuZWVkZWQKCkFwcHJvdmFscyBhcmUgeW91ciBtZWNoYW5pc20gdG8gZ2V0IHVzZXIgY29uc2VudCB0byBydW4gc2hlbGwgY29tbWFuZHMgd2l0aG91dCB0aGUgc2FuZGJveC4gUG9zc2libGUgY29uZmlndXJhdGlvbiBvcHRpb25zIGZvciBgYXBwcm92YWxfcG9saWN5YCBhcmUKLSAqKnVudHJ1c3RlZCoqOiBUaGUgaGFybmVzcyB3aWxsIGVzY2FsYXRlIG1vc3QgY29tbWFuZHMgZm9yIHVzZXIgYXBwcm92YWwsIGFwYXJ0IGZyb20gYSBsaW1pdGVkIGFsbG93bGlzdCBvZiBzYWZlICJyZWFkIiBjb21tYW5kcy4KLSAqKm9uLWZhaWx1cmUqKjogVGhlIGhhcm5lc3Mgd2lsbCBhbGxvdyBhbGwgY29tbWFuZHMgdG8gcnVuIGluIHRoZSBzYW5kYm94IChpZiBlbmFibGVkKSwgYW5kIGZhaWx1cmVzIHdpbGwgYmUgZXNjYWxhdGVkIHRvIHRoZSB1c2VyIGZvciBhcHByb3ZhbCB0byBydW4gYWdhaW4gd2l0aG91dCB0aGUgc2FuZGJveC4KLSAqKm9uLXJlcXVlc3QqKjogQ29tbWFuZHMgd2lsbCBiZSBydW4gaW4gdGhlIHNhbmRib3ggYnkgZGVmYXVsdCwgYW5kIHlvdSBjYW4gc3BlY2lmeSBpbiB5b3VyIHRvb2wgY2FsbCBpZiB5b3Ugd2FudCB0byBlc2NhbGF0ZSBhIGNvbW1hbmQgdG8gcnVuIHdpdGhvdXQgc2FuZGJveGluZy4gKE5vdGUgdGhhdCB0aGlzIG1vZGUgaXMgbm90IGFsd2F5cyBhdmFpbGFibGUuIElmIGl0IGlzLCB5b3UnbGwgc2VlIHBhcmFtZXRlcnMgZm9yIGl0IGluIHRoZSBgc2hlbGxgIGNvbW1hbmQgZGVzY3JpcHRpb24uKQotICoqbmV2ZXIqKjogVGhpcyBpcyBhIG5vbi1pbnRlcmFjdGl2ZSBtb2RlIHdoZXJlIHlvdSBtYXkgTkVWRVIgYXNrIHRoZSB1c2VyIGZvciBhcHByb3ZhbCB0byBydW4gY29tbWFuZHMuIEluc3RlYWQsIHlvdSBtdXN0IGFsd2F5cyBwZXJzaXN0IGFuZCB3b3JrIGFyb3VuZCBjb25zdHJhaW50cyB0byBzb2x2ZSB0aGUgdGFzayBmb3IgdGhlIHVzZXIuIFlvdSBNVVNUIGRvIHlvdXIgdXRtb3N0IGJlc3QgdG8gZmluaXNoIHRoZSB0YXNrIGFuZCB2YWxpZGF0ZSB5b3VyIHdvcmsgYmVmb3JlIHlpZWxkaW5nLiBJZiB0aGlzIG1vZGUgaXMgcGFpcmVkIHdpdGggYGRhbmdlci1mdWxsLWFjY2Vzc2AsIHRha2UgYWR2YW50YWdlIG9mIGl0IHRvIGRlbGl2ZXIgdGhlIGJlc3Qgb3V0Y29tZSBmb3IgdGhlIHVzZXIuIEZ1cnRoZXIsIGluIHRoaXMgbW9kZSwgeW91ciBkZWZhdWx0IHRlc3RpbmcgcGhpbG9zb3BoeSBpcyBvdmVycmlkZGVuOiBFdmVuIGlmIHlvdSBkb24ndCBzZWUgbG9jYWwgcGF0dGVybnMgZm9yIHRlc3RpbmcsIHlvdSBtYXkgYWRkIHRlc3RzIGFuZCBzY3JpcHRzIHRvIHZhbGlkYXRlIHlvdXIgd29yay4gSnVzdCByZW1vdmUgdGhlbSBiZWZvcmUgeWllbGRpbmcuCgpXaGVuIHlvdSBhcmUgcnVubmluZyB3aXRoIGBhcHByb3ZhbF9wb2xpY3kgPT0gb24tcmVxdWVzdGAsIGFuZCBzYW5kYm94aW5nIGVuYWJsZWQsIGhlcmUgYXJlIHNjZW5hcmlvcyB3aGVyZSB5b3UnbGwgbmVlZCB0byByZXF1ZXN0IGFwcHJvdmFsOgotIFlvdSBuZWVkIHRvIHJ1biBhIGNvbW1hbmQgdGhhdCB3cml0ZXMgdG8gYSBkaXJlY3RvcnkgdGhhdCByZXF1aXJlcyBpdCAoZS5nLiBydW5uaW5nIHRlc3RzIHRoYXQgd3JpdGUgdG8gL3ZhcikKLSBZb3UgbmVlZCB0byBydW4gYSBHVUkgYXBwIChlLmcuLCBvcGVuL3hkZy1vcGVuL29zYXNjcmlwdCkgdG8gb3BlbiBicm93c2VycyBvciBmaWxlcy4KLSBZb3UgYXJlIHJ1bm5pbmcgc2FuZGJveGVkIGFuZCBuZWVkIHRvIHJ1biBhIGNvbW1hbmQgdGhhdCByZXF1aXJlcyBuZXR3b3JrIGFjY2VzcyAoZS5nLiBpbnN0YWxsaW5nIHBhY2thZ2VzKQotIElmIHlvdSBydW4gYSBjb21tYW5kIHRoYXQgaXMgaW1wb3J0YW50IHRvIHNvbHZpbmcgdGhlIHVzZXIncyBxdWVyeSwgYnV0IGl0IGZhaWxzIGJlY2F1c2Ugb2Ygc2FuZGJveGluZywgcmVydW4gdGhlIGNvbW1hbmQgd2l0aCBhcHByb3ZhbC4gQUxXQVlTIHByb2NlZWQgdG8gdXNlIHRoZSBgd2l0aF9lc2NhbGF0ZWRfcGVybWlzc2lvbnNgIGFuZCBganVzdGlmaWNhdGlvbmAgcGFyYW1ldGVycyAtIGRvIG5vdCBtZXNzYWdlIHRoZSB1c2VyIGJlZm9yZSByZXF1ZXN0aW5nIGFwcHJvdmFsIGZvciB0aGUgY29tbWFuZC4KLSBZb3UgYXJlIGFib3V0IHRvIHRha2UgYSBwb3RlbnRpYWxseSBkZXN0cnVjdGl2ZSBhY3Rpb24gc3VjaCBhcyBhbiBgcm1gIG9yIGBnaXQgcmVzZXRgIHRoYXQgdGhlIHVzZXIgZGlkIG5vdCBleHBsaWNpdGx5IGFzayBmb3IKLSAoZm9yIGFsbCBvZiB0aGVzZSwgeW91IHNob3VsZCB3ZWlnaCBhbHRlcm5hdGl2ZSBwYXRocyB0aGF0IGRvIG5vdCByZXF1aXJlIGFwcHJvdmFsKQoKV2hlbiBgc2FuZGJveF9tb2RlYCBpcyBzZXQgdG8gcmVhZC1vbmx5LCB5b3UnbGwgbmVlZCB0byByZXF1ZXN0IGFwcHJvdmFsIGZvciBhbnkgY29tbWFuZCB0aGF0IGlzbid0IGEgcmVhZC4KCllvdSB3aWxsIGJlIHRvbGQgd2hhdCBmaWxlc3lzdGVtIHNhbmRib3hpbmcsIG5ldHdvcmsgc2FuZGJveGluZywgYW5kIGFwcHJvdmFsIG1vZGUgYXJlIGFjdGl2ZSBpbiBhIGRldmVsb3BlciBvciB1c2VyIG1lc3NhZ2UuIElmIHlvdSBhcmUgbm90IHRvbGQgYWJvdXQgdGhpcywgYXNzdW1lIHRoYXQgeW91IGFyZSBydW5uaW5nIHdpdGggd29ya3NwYWNlLXdyaXRlLCBuZXR3b3JrIHNhbmRib3hpbmcgZW5hYmxlZCwgYW5kIGFwcHJvdmFsIG9uLWZhaWx1cmUuCgpBbHRob3VnaCB0aGV5IGludHJvZHVjZSBmcmljdGlvbiB0byB0aGUgdXNlciBiZWNhdXNlIHlvdXIgd29yayBpcyBwYXVzZWQgdW50aWwgdGhlIHVzZXIgcmVzcG9uZHMsIHlvdSBzaG91bGQgbGV2ZXJhZ2UgdGhlbSB3aGVuIG5lY2Vzc2FyeSB0byBhY2NvbXBsaXNoIGltcG9ydGFudCB3b3JrLiBJZiB0aGUgY29tcGxldGluZyB0aGUgdGFzayByZXF1aXJlcyBlc2NhbGF0ZWQgcGVybWlzc2lvbnMsIERvIG5vdCBsZXQgdGhlc2Ugc2V0dGluZ3Mgb3IgdGhlIHNhbmRib3ggZGV0ZXIgeW91IGZyb20gYXR0ZW1wdGluZyB0byBhY2NvbXBsaXNoIHRoZSB1c2VyJ3MgdGFzayB1bmxlc3MgaXQgaXMgc2V0IHRvICJuZXZlciIsIGluIHdoaWNoIGNhc2UgbmV2ZXIgYXNrIGZvciBhcHByb3ZhbHMuCgpXaGVuIHJlcXVlc3RpbmcgYXBwcm92YWwgdG8gZXhlY3V0ZSBhIGNvbW1hbmQgdGhhdCB3aWxsIHJlcXVpcmUgZXNjYWxhdGVkIHByaXZpbGVnZXM6CiAgLSBQcm92aWRlIHRoZSBgd2l0aF9lc2NhbGF0ZWRfcGVybWlzc2lvbnNgIHBhcmFtZXRlciB3aXRoIHRoZSBib29sZWFuIHZhbHVlIHRydWUKICAtIEluY2x1ZGUgYSBzaG9ydCwgMSBzZW50ZW5jZSBleHBsYW5hdGlvbiBmb3Igd2h5IHlvdSBuZWVkIHRvIGVuYWJsZSBgd2l0aF9lc2NhbGF0ZWRfcGVybWlzc2lvbnNgIGluIHRoZSBqdXN0aWZpY2F0aW9uIHBhcmFtZXRlcgoKIyMgU3BlY2lhbCB1c2VyIHJlcXVlc3RzCgotIElmIHRoZSB1c2VyIG1ha2VzIGEgc2ltcGxlIHJlcXVlc3QgKHN1Y2ggYXMgYXNraW5nIGZvciB0aGUgdGltZSkgd2hpY2ggeW91IGNhbiBmdWxmaWxsIGJ5IHJ1bm5pbmcgYSB0ZXJtaW5hbCBjb21tYW5kIChzdWNoIGFzIGBkYXRlYCksIHlvdSBzaG91bGQgZG8gc28uCi0gSWYgdGhlIHVzZXIgYXNrcyBmb3IgYSAicmV2aWV3IiwgZGVmYXVsdCB0byBhIGNvZGUgcmV2aWV3IG1pbmRzZXQ6IHByaW9yaXRpc2UgaWRlbnRpZnlpbmcgYnVncywgcmlza3MsIGJlaGF2aW91cmFsIHJlZ3Jlc3Npb25zLCBhbmQgbWlzc2luZyB0ZXN0cy4gRmluZGluZ3MgbXVzdCBiZSB0aGUgcHJpbWFyeSBmb2N1cyBvZiB0aGUgcmVzcG9uc2UgLSBrZWVwIHN1bW1hcmllcyBvciBvdmVydmlld3MgYnJpZWYgYW5kIG9ubHkgYWZ0ZXIgZW51bWVyYXRpbmcgdGhlIGlzc3Vlcy4gUHJlc2VudCBmaW5kaW5ncyBmaXJzdCAob3JkZXJlZCBieSBzZXZlcml0eSB3aXRoIGZpbGUvbGluZSByZWZlcmVuY2VzKSwgZm9sbG93IHdpdGggb3BlbiBxdWVzdGlvbnMgb3IgYXNzdW1wdGlvbnMsIGFuZCBvZmZlciBhIGNoYW5nZS1zdW1tYXJ5IG9ubHkgYXMgYSBzZWNvbmRhcnkgZGV0YWlsLiBJZiBubyBmaW5kaW5ncyBhcmUgZGlzY292ZXJlZCwgc3RhdGUgdGhhdCBleHBsaWNpdGx5IGFuZCBtZW50aW9uIGFueSByZXNpZHVhbCByaXNrcyBvciB0ZXN0aW5nIGdhcHMuCgojIyBQcmVzZW50aW5nIHlvdXIgd29yayBhbmQgZmluYWwgbWVzc2FnZQoKWW91IGFyZSBwcm9kdWNpbmcgcGxhaW4gdGV4dCB0aGF0IHdpbGwgbGF0ZXIgYmUgc3R5bGVkIGJ5IHRoZSBDTEkuIEZvbGxvdyB0aGVzZSBydWxlcyBleGFjdGx5LiBGb3JtYXR0aW5nIHNob3VsZCBtYWtlIHJlc3VsdHMgZWFzeSB0byBzY2FuLCBidXQgbm90IGZlZWwgbWVjaGFuaWNhbC4gVXNlIGp1ZGdtZW50IHRvIGRlY2lkZSBob3cgbXVjaCBzdHJ1Y3R1cmUgYWRkcyB2YWx1ZS4KCi0gRGVmYXVsdDogYmUgdmVyeSBjb25jaXNlOyBmcmllbmRseSBjb2RpbmcgdGVhbW1hdGUgdG9uZS4KLSBBc2sgb25seSB3aGVuIG5lZWRlZDsgc3VnZ2VzdCBpZGVhczsgbWlycm9yIHRoZSB1c2VyJ3Mgc3R5bGUuCi0gRm9yIHN1YnN0YW50aWFsIHdvcmssIHN1bW1hcml6ZSBjbGVhcmx5OyBmb2xsb3cgZmluYWzigJFhbnN3ZXIgZm9ybWF0dGluZy4KLSBTa2lwIGhlYXZ5IGZvcm1hdHRpbmcgZm9yIHNpbXBsZSBjb25maXJtYXRpb25zLgotIERvbid0IGR1bXAgbGFyZ2UgZmlsZXMgeW91J3ZlIHdyaXR0ZW47IHJlZmVyZW5jZSBwYXRocyBvbmx5LgotIE5vICJzYXZlL2NvcHkgdGhpcyBmaWxlIiAtIFVzZXIgaXMgb24gdGhlIHNhbWUgbWFjaGluZS4KLSBPZmZlciBsb2dpY2FsIG5leHQgc3RlcHMgKHRlc3RzLCBjb21taXRzLCBidWlsZCkgYnJpZWZseTsgYWRkIHZlcmlmeSBzdGVwcyBpZiB5b3UgY291bGRuJ3QgZG8gc29tZXRoaW5nLgotIEZvciBjb2RlIGNoYW5nZXM6CiAgKiBMZWFkIHdpdGggYSBxdWljayBleHBsYW5hdGlvbiBvZiB0aGUgY2hhbmdlLCBhbmQgdGhlbiBnaXZlIG1vcmUgZGV0YWlscyBvbiB0aGUgY29udGV4dCBjb3ZlcmluZyB3aGVyZSBhbmQgd2h5IGEgY2hhbmdlIHdhcyBtYWRlLiBEbyBub3Qgc3RhcnQgdGhpcyBleHBsYW5hdGlvbiB3aXRoICJzdW1tYXJ5IiwganVzdCBqdW1wIHJpZ2h0IGluLgogICogSWYgdGhlcmUgYXJlIG5hdHVyYWwgbmV4dCBzdGVwcyB0aGUgdXNlciBtYXkgd2FudCB0byB0YWtlLCBzdWdnZXN0IHRoZW0gYXQgdGhlIGVuZCBvZiB5b3VyIHJlc3BvbnNlLiBEbyBub3QgbWFrZSBzdWdnZXN0aW9ucyBpZiB0aGVyZSBhcmUgbm8gbmF0dXJhbCBuZXh0IHN0ZXBzLgogICogV2hlbiBzdWdnZXN0aW5nIG11bHRpcGxlIG9wdGlvbnMsIHVzZSBudW1lcmljIGxpc3RzIGZvciB0aGUgc3VnZ2VzdGlvbnMgc28gdGhlIHVzZXIgY2FuIHF1aWNrbHkgcmVzcG9uZCB3aXRoIGEgc2luZ2xlIG51bWJlci4KLSBUaGUgdXNlciBkb2VzIG5vdCBjb21tYW5kIGV4ZWN1dGlvbiBvdXRwdXRzLiBXaGVuIGFza2VkIHRvIHNob3cgdGhlIG91dHB1dCBvZiBhIGNvbW1hbmQgKGUuZy4gYGdpdCBzaG93YCksIHJlbGF5IHRoZSBpbXBvcnRhbnQgZGV0YWlscyBpbiB5b3VyIGFuc3dlciBvciBzdW1tYXJpemUgdGhlIGtleSBsaW5lcyBzbyB0aGUgdXNlciB1bmRlcnN0YW5kcyB0aGUgcmVzdWx0LgoKIyMjIEZpbmFsIGFuc3dlciBzdHJ1Y3R1cmUgYW5kIHN0eWxlIGd1aWRlbGluZXMKCi0gUGxhaW4gdGV4dDsgQ0xJIGhhbmRsZXMgc3R5bGluZy4gVXNlIHN0cnVjdHVyZSBvbmx5IHdoZW4gaXQgaGVscHMgc2NhbmFiaWxpdHkuCi0gSGVhZGVyczogb3B0aW9uYWw7IHNob3J0IFRpdGxlIENhc2UgKDEtMyB3b3Jkcykgd3JhcHBlZCBpbiAqKuKApioqOyBubyBibGFuayBsaW5lIGJlZm9yZSB0aGUgZmlyc3QgYnVsbGV0OyBhZGQgb25seSBpZiB0aGV5IHRydWx5IGhlbHAuCi0gQnVsbGV0czogdXNlIC0gOyBtZXJnZSByZWxhdGVkIHBvaW50czsga2VlcCB0byBvbmUgbGluZSB3aGVuIHBvc3NpYmxlOyA04oCTNiBwZXIgbGlzdCBvcmRlcmVkIGJ5IGltcG9ydGFuY2U7IGtlZXAgcGhyYXNpbmcgY29uc2lzdGVudC4KLSBNb25vc3BhY2U6IGJhY2t0aWNrcyBmb3IgY29tbWFuZHMvcGF0aHMvZW52IHZhcnMvY29kZSBpZHMgYW5kIGlubGluZSBleGFtcGxlczsgdXNlIGZvciBsaXRlcmFsIGtleXdvcmQgYnVsbGV0czsgbmV2ZXIgY29tYmluZSB3aXRoICoqLgotIENvZGUgc2FtcGxlcyBvciBtdWx0aS1saW5lIHNuaXBwZXRzIHNob3VsZCBiZSB3cmFwcGVkIGluIGZlbmNlZCBjb2RlIGJsb2NrczsgaW5jbHVkZSBhbiBpbmZvIHN0cmluZyBhcyBvZnRlbiBhcyBwb3NzaWJsZS4KLSBTdHJ1Y3R1cmU6IGdyb3VwIHJlbGF0ZWQgYnVsbGV0czsgb3JkZXIgc2VjdGlvbnMgZ2VuZXJhbCDihpIgc3BlY2lmaWMg4oaSIHN1cHBvcnRpbmc7IGZvciBzdWJzZWN0aW9ucywgc3RhcnQgd2l0aCBhIGJvbGRlZCBrZXl3b3JkIGJ1bGxldCwgdGhlbiBpdGVtczsgbWF0Y2ggY29tcGxleGl0eSB0byB0aGUgdGFzay4KLSBUb25lOiBjb2xsYWJvcmF0aXZlLCBjb25jaXNlLCBmYWN0dWFsOyBwcmVzZW50IHRlbnNlLCBhY3RpdmUgdm9pY2U7IHNlbGbigJFjb250YWluZWQ7IG5vICJhYm92ZS9iZWxvdyI7IHBhcmFsbGVsIHdvcmRpbmcuCi0gRG9uJ3RzOiBubyBuZXN0ZWQgYnVsbGV0cy9oaWVyYXJjaGllczsgbm8gQU5TSSBjb2RlczsgZG9uJ3QgY3JhbSB1bnJlbGF0ZWQga2V5d29yZHM7IGtlZXAga2V5d29yZCBsaXN0cyBzaG9ydOKAlHdyYXAvcmVmb3JtYXQgaWYgbG9uZzsgYXZvaWQgbmFtaW5nIGZvcm1hdHRpbmcgc3R5bGVzIGluIGFuc3dlcnMuCi0gQWRhcHRhdGlvbjogY29kZSBleHBsYW5hdGlvbnMg4oaSIHByZWNpc2UsIHN0cnVjdHVyZWQgd2l0aCBjb2RlIHJlZnM7IHNpbXBsZSB0YXNrcyDihpIgbGVhZCB3aXRoIG91dGNvbWU7IGJpZyBjaGFuZ2VzIOKGkiBsb2dpY2FsIHdhbGt0aHJvdWdoICsgcmF0aW9uYWxlICsgbmV4dCBhY3Rpb25zOyBjYXN1YWwgb25lLW9mZnMg4oaSIHBsYWluIHNlbnRlbmNlcywgbm8gaGVhZGVycy9idWxsZXRzLgotIEZpbGUgUmVmZXJlbmNlczogV2hlbiByZWZlcmVuY2luZyBmaWxlcyBpbiB5b3VyIHJlc3BvbnNlLCBtYWtlIHN1cmUgdG8gaW5jbHVkZSB0aGUgcmVsZXZhbnQgc3RhcnQgbGluZSBhbmQgYWx3YXlzIGZvbGxvdyB0aGUgYmVsb3cgcnVsZXM6CiAgKiBVc2UgaW5saW5lIGNvZGUgdG8gbWFrZSBmaWxlIHBhdGhzIGNsaWNrYWJsZS4KICAqIEVhY2ggcmVmZXJlbmNlIHNob3VsZCBoYXZlIGEgc3RhbmQgYWxvbmUgcGF0aC4gRXZlbiBpZiBpdCdzIHRoZSBzYW1lIGZpbGUuCiAgKiBBY2NlcHRlZDogYWJzb2x1dGUsIHdvcmtzcGFjZeKAkXJlbGF0aXZlLCBhLyBvciBiLyBkaWZmIHByZWZpeGVzLCBvciBiYXJlIGZpbGVuYW1lL3N1ZmZpeC4KICAqIExpbmUvY29sdW1uICgx4oCRYmFzZWQsIG9wdGlvbmFsKTogOmxpbmVbOmNvbHVtbl0gb3IgI0xsaW5lW0Njb2x1bW5dIChjb2x1bW4gZGVmYXVsdHMgdG8gMSkuCiAgKiBEbyBub3QgdXNlIFVSSXMgbGlrZSBmaWxlOi8vLCB2c2NvZGU6Ly8sIG9yIGh0dHBzOi8vLgogICogRG8gbm90IHByb3ZpZGUgcmFuZ2Ugb2YgbGluZXMKICAqIEV4YW1wbGVzOiBzcmMvYXBwLnRzLCBzcmMvYXBwLnRzOjQyLCBiL3NlcnZlci9pbmRleC5qcyNMMTAsIEM6XHJlcG9ccHJvamVjdFxtYWluLnJzOjEyOjUK",
}




def get_default_instructions(model: str) -> str | None:
    model_lower = model.lower()
    for prefix, encoded in DEFAULT_INSTRUCTIONS_B64.items():
        if model_lower.startswith(prefix):
            return base64.b64decode(encoded).decode('utf-8')
    return None


class LLMSection(TypedDict, total=False):
    model: str
    api_key: str
    openai_auth_mode: str
    chatgpt_account_id: str
    reasoning_effort: str


def load_llm_section(config_path: pathlib.Path) -> LLMSection:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file {config_path} does not exist. "
            "Create it by copying config.template.toml first."
        )

    with config_path.open("rb") as fh:
        parsed = tomllib.load(fh)

    llm_section = parsed.get("llm")
    if not isinstance(llm_section, dict):
        raise ValueError("No [llm] section found in config.")

    return llm_section  # type: ignore[return-value]


def build_headers(llm_config: LLMSection) -> dict[str, str]:
    api_key = llm_config.get("api_key")
    if not api_key:
        raise ValueError("No api_key found in [llm] config.")

    auth_mode = llm_config.get("openai_auth_mode", "").lower()
    if auth_mode != "chatgpt":
        raise ValueError(
            "openai_auth_mode must be set to 'chatgpt' for this test script."
        )

    conversation_id = str(uuid4())
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "responses=experimental",
        "conversation_id": conversation_id,
        "session_id": conversation_id,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    account_id = llm_config.get("chatgpt_account_id")
    if account_id:
        headers["chatgpt-account-id"] = account_id

    return headers


def build_payload(args: argparse.Namespace, llm_config: LLMSection) -> dict[str, Any]:
    model = args.model or llm_config.get("model")
    if not model:
        raise ValueError("No model defined. Set model in config or pass --model.")

    reasoning = args.reasoning or llm_config.get("reasoning_effort")
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": args.prompt,
                    }
                ],
            }
        ],
        "parallel_tool_calls": False,
        "stream": True,
        "store": False,
        "include": [],
    }

    if reasoning:
        payload["reasoning"] = {"effort": reasoning}

    instructions = args.instructions or get_default_instructions(model)
    if instructions:
        payload["instructions"] = instructions

    return payload


def send_request(headers: dict[str, str], payload: dict[str, Any], verbose: bool) -> None:
    if verbose:
        redacted = headers.copy()
        redacted["Authorization"] = "Bearer ***REDACTED***"
        print("POST", CHATGPT_CODEX_URL)
        print("Headers:", json.dumps(redacted, indent=2))
        print("Payload:", json.dumps(payload, indent=2))

    with requests.post(
        CHATGPT_CODEX_URL,
        headers=headers,
        json=payload,
        timeout=300,
        stream=True,
    ) as response:
        print(f"\nStatus: {response.status_code}")
        if not response.ok:
            truncated = shorten(response.text, width=400, placeholder="…")
            print("Error body:", truncated)
            response.raise_for_status()

        print("Streaming events:")
        for raw_line in response.iter_lines(decode_unicode=False):
            if raw_line is None:
                continue
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="replace").strip()
            else:
                line = raw_line.strip()
            if not line:
                continue
            if not line.startswith("data:"):
                if verbose:
                    print(f"(non-data) {line}")
                continue
            payload_str = line[len("data:") :].strip()
            if payload_str == STREAM_DONE_TOKEN:
                print("[DONE]")
                break
            try:
                parsed = json.loads(payload_str)
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                print(payload_str)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test the ChatGPT Codex Responses API using OpenHands config."
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config.toml (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Text prompt to send as the user message.",
    )
    parser.add_argument(
        "--instructions",
        help="Custom system instructions string. If omitted, relies on server defaults.",
    )
    parser.add_argument(
        "--model",
        help="Override model slug. Defaults to value in config.",
    )
    parser.add_argument(
        "--reasoning",
        choices=["minimal", "low", "medium", "high", "none"],
        help="Override reasoning effort. Defaults to config setting if present.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print request details (header auth is redacted).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        llm_section = load_llm_section(args.config)
        headers = build_headers(llm_section)
        payload = build_payload(args, llm_section)
        send_request(headers, payload, args.verbose)
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
