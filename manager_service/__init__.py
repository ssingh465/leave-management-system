"""Manager Service: team leave views and approve/reject actions.

The Manager Service owns no data store. It reads and mutates leave requests
through the Leave Request Service API and deducts balances through the Leave
Balance Service API, so there are no dataclasses or stores defined here.
"""
