"""Use cases the UI calls: each write is one transaction and records itself in ``event_log``.

This is the imperative shell around ``core/``: it loads rows through ``storage/``, asks
``core/`` what should change, and writes the result. The UI never touches ``storage/``
directly. "Today" is always passed in; audit timestamps default to the current UTC time
but can be injected (``now=``) for tests.
"""
