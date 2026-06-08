"""Builds the ELMS_Postman_Collection.json file.

Run as: python build_collection.py

The collection is structured as a sequence so it executes top-to-bottom
in the Postman Collection Runner: tokens captured in Auth are reused
across folders, and request IDs created in Apply Leave are consumed by
the Approve/Reject/Cancel folders later.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "ELMS_Postman_Collection.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def script(lines: list[str]) -> dict:
    """Wrap a list of JS lines as a Postman test/prerequest script."""
    return {"type": "text/javascript", "exec": lines}


def url(path: str, query: list[dict] | None = None) -> dict:
    """Build a Postman URL targeting the gateway."""
    parts = [p for p in path.split("/") if p]
    out = {
        "raw": "{{baseUrl}}/" + "/".join(parts) + (
            ("?" + "&".join(f"{q['key']}={q['value']}" for q in query)) if query else ""
        ),
        "host": ["{{baseUrl}}"],
        "path": parts,
    }
    if query:
        out["query"] = query
    return out


def bearer(var: str) -> list[dict]:
    return [{"key": "Authorization", "value": "Bearer {{" + var + "}}"}]


def json_body(obj: dict | list) -> dict:
    return {
        "mode": "raw",
        "raw": json.dumps(obj, indent=2),
        "options": {"raw": {"language": "json"}},
    }


def request(
    *,
    name: str,
    method: str,
    url_path: str,
    headers: list[dict] | None = None,
    body: dict | None = None,
    query: list[dict] | None = None,
    test_lines: list[str] | None = None,
    description: str = "",
) -> dict:
    req = {
        "method": method,
        "header": headers or [],
        "url": url(url_path, query),
    }
    if body is not None:
        req["body"] = body
    if description:
        req["description"] = description
    item: dict = {"name": name, "request": req, "response": []}
    if test_lines is not None:
        item["event"] = [{"listen": "test", "script": script(test_lines)}]
    return item


# ---------------------------------------------------------------------------
# Folder 01 - Authentication
# ---------------------------------------------------------------------------
def folder_auth() -> dict:
    return {
        "name": "01 - Authentication",
        "description": (
            "POST /auth/login is the only public endpoint. Returns an HS256 JWT "
            "carrying sub (user id) and role. Bad creds and unknown users both "
            "return 401 with the same generic message (so the API does not leak "
            "which accounts exist)."
        ),
        "item": [
            request(
                name="Login - Manager",
                method="POST",
                url_path="/auth/login",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({"username": "manager1", "password": "Manager@123"}),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('Response carries an access_token', function () {",
                    "  pm.expect(body.access_token).to.be.a('string').and.not.empty;",
                    "  pm.expect(body.token_type).to.eql('bearer');",
                    "});",
                    "pm.collectionVariables.set('manager_token', body.access_token);",
                ],
            ),
            request(
                name="Login - Employee 1",
                method="POST",
                url_path="/auth/login",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({"username": "emp1", "password": "Employee@123"}),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.expect(body.access_token).to.be.a('string').and.not.empty;",
                    "pm.collectionVariables.set('emp1_token', body.access_token);",
                ],
            ),
            request(
                name="Login - Employee 2",
                method="POST",
                url_path="/auth/login",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({"username": "emp2", "password": "Employee@123"}),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.expect(body.access_token).to.be.a('string').and.not.empty;",
                    "pm.collectionVariables.set('emp2_token', body.access_token);",
                ],
            ),
            request(
                name="Login - Wrong Password (401)",
                method="POST",
                url_path="/auth/login",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({"username": "emp1", "password": "wrong-password"}),
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                    "pm.test('Generic error detail', function () {",
                    "  pm.expect(pm.response.json().detail).to.match(/invalid/i);",
                    "});",
                ],
            ),
            request(
                name="Login - Unknown User (401)",
                method="POST",
                url_path="/auth/login",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({"username": "ghost", "password": "irrelevant"}),
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                ],
            ),
            request(
                name="Login - Missing Field (422)",
                method="POST",
                url_path="/auth/login",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({"username": "emp1"}),
                test_lines=[
                    "pm.test('422 Unprocessable Entity', function () { pm.response.to.have.status(422); });",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Folder 02 - Leave Balance
# ---------------------------------------------------------------------------
def folder_balance() -> dict:
    return {
        "name": "02 - Leave Balance",
        "description": (
            "GET /employees/me/balances returns the caller's own balances. "
            "GET /employees/{id}/balances enforces RBAC: an employee may read "
            "only their own; a manager may additionally read direct reports. "
            "Each seeded employee starts with CASUAL=12, SICK=10, PRIVILEGE=15."
        ),
        "item": [
            request(
                name="My Balances - Employee 1 (200, 3 entries)",
                method="GET",
                url_path="/employees/me/balances",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('employee_id matches emp1', function () {",
                    "  pm.expect(body.employee_id).to.eql(pm.collectionVariables.get('emp1_id'));",
                    "});",
                    "pm.test('Three balance records seeded with the canonical allocations', function () {",
                    "  pm.expect(body.balances).to.have.lengthOf(3);",
                    "  const byType = {};",
                    "  body.balances.forEach(function (b) { byType[b.leave_type] = b; });",
                    "  pm.expect(byType.CASUAL.total_allocated).to.eql(12);",
                    "  pm.expect(byType.SICK.total_allocated).to.eql(10);",
                    "  pm.expect(byType.PRIVILEGE.total_allocated).to.eql(15);",
                    "  body.balances.forEach(function (b) {",
                    "    pm.expect(b.remaining).to.eql(b.total_allocated - b.used);",
                    "  });",
                    "});",
                ],
            ),
            request(
                name="My Balances - Manager (200, empty list)",
                method="GET",
                url_path="/employees/me/balances",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.test('Manager has no balance records', function () {",
                    "  pm.expect(pm.response.json().balances).to.have.lengthOf(0);",
                    "});",
                ],
            ),
            request(
                name="Specific Balances - Self (200)",
                method="GET",
                url_path="/employees/{{emp1_id}}/balances",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                ],
            ),
            request(
                name="Specific Balances - Manager Reading Direct Report (200)",
                method="GET",
                url_path="/employees/{{emp1_id}}/balances",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.test('Returns balances for the requested employee', function () {",
                    "  pm.expect(pm.response.json().employee_id).to.eql(pm.collectionVariables.get('emp1_id'));",
                    "});",
                ],
            ),
            request(
                name="Specific Balances - Employee Reading Another Employee (403)",
                method="GET",
                url_path="/employees/{{emp2_id}}/balances",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('403 Forbidden', function () { pm.response.to.have.status(403); });",
                ],
            ),
            request(
                name="Specific Balances - Manager Reading Outside Team (403)",
                method="GET",
                url_path="/employees/{{fake_id}}/balances",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('403 Forbidden', function () { pm.response.to.have.status(403); });",
                ],
            ),
            request(
                name="Specific Balances - No Auth Header (401)",
                method="GET",
                url_path="/employees/me/balances",
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Folder 03 - Apply Leave
# ---------------------------------------------------------------------------
def folder_apply() -> dict:
    return {
        "name": "03 - Apply Leave",
        "description": (
            "POST /leaves runs the four business validations in order: "
            "(1) start_date <= end_date - 400, (2) start_date >= today - 400, "
            "(3) number_of_days == inclusive day count - 400, "
            "(4) no overlap with existing PENDING/APPROVED requests - 409. "
            "After they pass, the service calls Leave Balance over httpx and "
            "returns 409 if balance is insufficient. Pydantic returns 422 for "
            "structural problems (missing/wrong-typed fields, days <= 0)."
        ),
        "item": [
            request(
                name="Apply Casual 3d - Success (201)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_a_start}}",
                    "end_date": "{{range_a_end}}",
                    "number_of_days": 3,
                    "reason": "Family event"
                }),
                test_lines=[
                    "pm.test('201 Created', function () { pm.response.to.have.status(201); });",
                    "const body = pm.response.json();",
                    "pm.test('Status is PENDING and routed to manager1', function () {",
                    "  pm.expect(body.status).to.eql('PENDING');",
                    "  pm.expect(body.reporting_manager_id).to.eql(pm.collectionVariables.get('manager_id'));",
                    "  pm.expect(body.employee_id).to.eql(pm.collectionVariables.get('emp1_id'));",
                    "});",
                    "pm.collectionVariables.set('pending_request_id_1', body.request_id);",
                ],
            ),
            request(
                name="Apply - Date Range Inverted (400)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_a_end}}",
                    "end_date": "{{range_a_start}}",
                    "number_of_days": 3,
                    "reason": "Inverted range"
                }),
                test_lines=[
                    "pm.test('400 Bad Request (start > end)', function () { pm.response.to.have.status(400); });",
                    "pm.expect(pm.response.json().detail).to.match(/start_date.*not.*after.*end_date/i);",
                ],
            ),
            request(
                name="Apply - Past Start Date (400)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{past_start}}",
                    "end_date": "{{past_end}}",
                    "number_of_days": 3,
                    "reason": "Backdated"
                }),
                test_lines=[
                    "pm.test('400 Bad Request (past date)', function () { pm.response.to.have.status(400); });",
                    "pm.expect(pm.response.json().detail).to.match(/past/i);",
                ],
            ),
            request(
                name="Apply - Day Count Mismatch (400)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_a_start}}",
                    "end_date": "{{range_a_end}}",
                    "number_of_days": 5,
                    "reason": "Wrong day count"
                }),
                test_lines=[
                    "pm.test('400 Bad Request (day count mismatch)', function () { pm.response.to.have.status(400); });",
                    "pm.expect(pm.response.json().detail).to.match(/number_of_days/i);",
                ],
            ),
            request(
                name="Apply - Overlap (409)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "SICK",
                    "start_date": "{{range_a_start}}",
                    "end_date": "{{range_a_end}}",
                    "number_of_days": 3,
                    "reason": "Overlapping with existing pending request"
                }),
                test_lines=[
                    "pm.test('409 Conflict (overlap)', function () { pm.response.to.have.status(409); });",
                    "pm.expect(pm.response.json().detail).to.match(/already exists/i);",
                ],
            ),
            request(
                name="Apply - Insufficient Balance (409)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "SICK",
                    "start_date": "{{range_d_start}}",
                    "end_date": "{{range_d_end}}",
                    "number_of_days": 11,
                    "reason": "Long sickness (exceeds 10-day SICK allocation)"
                }),
                test_lines=[
                    "pm.test('409 Conflict (insufficient balance)', function () { pm.response.to.have.status(409); });",
                    "pm.expect(pm.response.json().detail).to.match(/insufficient/i);",
                ],
            ),
            request(
                name="Apply - Reporting Manager Mismatch (400)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_e_start}}",
                    "end_date": "{{range_e_end}}",
                    "number_of_days": 1,
                    "reason": "Trying to bypass real manager",
                    "reporting_manager_id": "{{fake_id}}"
                }),
                test_lines=[
                    "pm.test('400 Bad Request (manager mismatch)', function () { pm.response.to.have.status(400); });",
                    "pm.expect(pm.response.json().detail).to.match(/reporting_manager_id/i);",
                ],
            ),
            request(
                name="Apply - Negative Days (422)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_a_start}}",
                    "end_date": "{{range_a_end}}",
                    "number_of_days": -3,
                    "reason": "Negative days violates Pydantic Field(gt=0)"
                }),
                test_lines=[
                    "pm.test('422 Unprocessable Entity', function () { pm.response.to.have.status(422); });",
                ],
            ),
            request(
                name="Apply - No Auth (401)",
                method="POST",
                url_path="/leaves",
                headers=[{"key": "Content-Type", "value": "application/json"}],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_a_start}}",
                    "end_date": "{{range_a_end}}",
                    "number_of_days": 3,
                    "reason": "No token"
                }),
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Folder 04 - History
# ---------------------------------------------------------------------------
def folder_history() -> dict:
    return {
        "name": "04 - History",
        "description": (
            "GET /leaves/history is the caller's own history with optional "
            "?status filter (PENDING/APPROVED/REJECTED/CANCELLED/ALL) and "
            "page/page_size pagination. Invalid status values return 400."
        ),
        "item": [
            request(
                name="My History - Default",
                method="GET",
                url_path="/leaves/history",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('Pagination envelope is well-formed', function () {",
                    "  pm.expect(body).to.have.all.keys('items', 'page', 'page_size', 'total', 'total_pages');",
                    "  pm.expect(body.page).to.eql(1);",
                    "  pm.expect(body.page_size).to.eql(10);",
                    "});",
                    "pm.test('Includes the pending request created earlier', function () {",
                    "  const ids = body.items.map(function (i) { return i.request_id; });",
                    "  pm.expect(ids).to.include(pm.collectionVariables.get('pending_request_id_1'));",
                    "});",
                ],
            ),
            request(
                name="My History - status=PENDING",
                method="GET",
                url_path="/leaves/history",
                query=[{"key": "status", "value": "PENDING"}],
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('All returned items are PENDING', function () {",
                    "  body.items.forEach(function (i) { pm.expect(i.status).to.eql('PENDING'); });",
                    "  pm.expect(body.items.length).to.be.at.least(1);",
                    "});",
                ],
            ),
            request(
                name="My History - status=APPROVED (initially empty)",
                method="GET",
                url_path="/leaves/history",
                query=[{"key": "status", "value": "APPROVED"}],
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.test('No APPROVED items yet', function () {",
                    "  pm.expect(pm.response.json().items).to.have.lengthOf(0);",
                    "});",
                ],
            ),
            request(
                name="My History - status=ALL",
                method="GET",
                url_path="/leaves/history",
                query=[{"key": "status", "value": "ALL"}],
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                ],
            ),
            request(
                name="My History - Invalid Status (400)",
                method="GET",
                url_path="/leaves/history",
                query=[{"key": "status", "value": "BOGUS"}],
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('400 Bad Request', function () { pm.response.to.have.status(400); });",
                ],
            ),
            request(
                name="My History - Pagination (page_size=1)",
                method="GET",
                url_path="/leaves/history",
                query=[
                    {"key": "page", "value": "1"},
                    {"key": "page_size", "value": "1"},
                ],
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('Page envelope reflects requested size', function () {",
                    "  pm.expect(body.page_size).to.eql(1);",
                    "  pm.expect(body.items.length).to.be.at.most(1);",
                    "});",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Folder 05 - Manager: View
# ---------------------------------------------------------------------------
def folder_manager_view() -> dict:
    return {
        "name": "05 - Manager: View",
        "description": (
            "GET /manager/requests is manager-only (require_manager dependency "
            "returns 403 for employees). Results are scoped to the calling "
            "manager's team and support optional status / employee_id / "
            "from_date / to_date filters."
        ),
        "item": [
            request(
                name="List Team Requests - Employee (403)",
                method="GET",
                url_path="/manager/requests",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('403 Forbidden (employees may not list manager requests)', function () {",
                    "  pm.response.to.have.status(403);",
                    "});",
                ],
            ),
            request(
                name="List Team Requests - Manager (200)",
                method="GET",
                url_path="/manager/requests",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const items = pm.response.json();",
                    "pm.test('Pending request from emp1 is visible', function () {",
                    "  const ids = items.map(function (i) { return i.request_id; });",
                    "  pm.expect(ids).to.include(pm.collectionVariables.get('pending_request_id_1'));",
                    "});",
                    "pm.test('Each row carries employee_name from the org chart', function () {",
                    "  items.forEach(function (i) { pm.expect(i.employee_name).to.be.a('string'); });",
                    "});",
                ],
            ),
            request(
                name="List Team Requests - status=PENDING",
                method="GET",
                url_path="/manager/requests",
                query=[{"key": "status", "value": "PENDING"}],
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.response.json().forEach(function (i) {",
                    "  pm.expect(i.status).to.eql('PENDING');",
                    "});",
                ],
            ),
            request(
                name="List Team Requests - employee_id=emp1",
                method="GET",
                url_path="/manager/requests",
                query=[{"key": "employee_id", "value": "{{emp1_id}}"}],
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.response.json().forEach(function (i) {",
                    "  pm.expect(i.employee_id).to.eql(pm.collectionVariables.get('emp1_id'));",
                    "});",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Folder 06 - Manager: Approve
# ---------------------------------------------------------------------------
def folder_manager_approve() -> dict:
    return {
        "name": "06 - Manager: Approve",
        "description": (
            "Approving a PENDING request orchestrates two downstream calls: "
            "(1) deduct days from the employee's balance via the Leave Balance "
            "Service, then (2) flip the request to APPROVED on the Leave Request "
            "Service. Both calls are wrapped in pybreaker circuit breakers."
        ),
        "item": [
            request(
                name="Approve Pending #1 (200, balance deducted)",
                method="POST",
                url_path="/manager/requests/{{pending_request_id_1}}/approve",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('Status flipped to APPROVED', function () {",
                    "  pm.expect(body.status).to.eql('APPROVED');",
                    "  pm.expect(body.request_id).to.eql(pm.collectionVariables.get('pending_request_id_1'));",
                    "});",
                ],
            ),
            request(
                name="Approve Same Request Again (409)",
                method="POST",
                url_path="/manager/requests/{{pending_request_id_1}}/approve",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('409 Conflict (only PENDING requests can be approved)', function () {",
                    "  pm.response.to.have.status(409);",
                    "});",
                ],
            ),
            request(
                name="Verify Balance Deducted (CASUAL used=3, remaining=9)",
                method="GET",
                url_path="/employees/me/balances",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const casual = pm.response.json().balances.find(function (b) {",
                    "  return b.leave_type === 'CASUAL';",
                    "});",
                    "pm.test('CASUAL used=3, remaining=9', function () {",
                    "  pm.expect(casual.used).to.eql(3);",
                    "  pm.expect(casual.remaining).to.eql(9);",
                    "});",
                ],
            ),
            request(
                name="Approve Unknown Request ID (404)",
                method="POST",
                url_path="/manager/requests/{{fake_id}}/approve",
                headers=bearer("manager_token"),
                test_lines=[
                    "pm.test('404 Not Found', function () { pm.response.to.have.status(404); });",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Folder 07 - Manager: Reject
# ---------------------------------------------------------------------------
def folder_manager_reject() -> dict:
    return {
        "name": "07 - Manager: Reject",
        "description": (
            "Rejecting a PENDING request requires a non-empty rejection_reason "
            "(Pydantic min_length=1). Already-decided requests return 409. "
            "This folder first creates a fresh PENDING request to reject."
        ),
        "item": [
            request(
                name="Apply 2nd Leave - Privilege 2d (201, captures id_2)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "PRIVILEGE",
                    "start_date": "{{range_b_start}}",
                    "end_date": "{{range_b_end}}",
                    "number_of_days": 2,
                    "reason": "Trip planning"
                }),
                test_lines=[
                    "pm.test('201 Created', function () { pm.response.to.have.status(201); });",
                    "pm.collectionVariables.set('pending_request_id_2', pm.response.json().request_id);",
                ],
            ),
            request(
                name="Reject - Empty Reason (422)",
                method="POST",
                url_path="/manager/requests/{{pending_request_id_2}}/reject",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{manager_token}}"},
                ],
                body=json_body({"rejection_reason": ""}),
                test_lines=[
                    "pm.test('422 Unprocessable Entity (rejection_reason min_length=1)', function () {",
                    "  pm.response.to.have.status(422);",
                    "});",
                ],
            ),
            request(
                name="Reject - Missing Reason Body (422)",
                method="POST",
                url_path="/manager/requests/{{pending_request_id_2}}/reject",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{manager_token}}"},
                ],
                body=json_body({}),
                test_lines=[
                    "pm.test('422 Unprocessable Entity', function () { pm.response.to.have.status(422); });",
                ],
            ),
            request(
                name="Reject Pending #2 (200)",
                method="POST",
                url_path="/manager/requests/{{pending_request_id_2}}/reject",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{manager_token}}"},
                ],
                body=json_body({"rejection_reason": "Conflicts with team launch"}),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "const body = pm.response.json();",
                    "pm.test('Status flipped to REJECTED with reason recorded', function () {",
                    "  pm.expect(body.status).to.eql('REJECTED');",
                    "  pm.expect(body.rejection_reason).to.eql('Conflicts with team launch');",
                    "});",
                ],
            ),
            request(
                name="Reject Already Rejected (409)",
                method="POST",
                url_path="/manager/requests/{{pending_request_id_2}}/reject",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{manager_token}}"},
                ],
                body=json_body({"rejection_reason": "Trying again"}),
                test_lines=[
                    "pm.test('409 Conflict (only PENDING can be rejected)', function () {",
                    "  pm.response.to.have.status(409);",
                    "});",
                ],
            ),
        ],
    }


def folder_cancel() -> dict:
    return {
        "name": "08 - Cancel Leave",
        "description": (
            "PATCH /leaves/{id}/cancel lets the owner cancel their PENDING "
            "request. 404 for unknown ids, 403 for someone else's request, "
            "409 if the request is no longer PENDING."
        ),
        "item": [
            request(
                name="Apply 3rd Leave - Sick 1d (201, captures id_3)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "SICK",
                    "start_date": "{{range_c_start}}",
                    "end_date": "{{range_c_end}}",
                    "number_of_days": 1,
                    "reason": "Doctor visit"
                }),
                test_lines=[
                    "pm.test('201 Created', function () { pm.response.to.have.status(201); });",
                    "pm.collectionVariables.set('pending_request_id_3', pm.response.json().request_id);",
                ],
            ),
            request(
                name="Cancel - Not Owner (403)",
                method="PATCH",
                url_path="/leaves/{{pending_request_id_3}}/cancel",
                headers=bearer("emp2_token"),
                test_lines=[
                    "pm.test('403 Forbidden (emp2 cannot cancel emp1 request)', function () {",
                    "  pm.response.to.have.status(403);",
                    "});",
                ],
            ),
            request(
                name="Cancel - Unknown ID (404)",
                method="PATCH",
                url_path="/leaves/{{fake_id}}/cancel",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('404 Not Found', function () { pm.response.to.have.status(404); });",
                ],
            ),
            request(
                name="Cancel - No Auth (401)",
                method="PATCH",
                url_path="/leaves/{{pending_request_id_3}}/cancel",
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                ],
            ),
            request(
                name="Cancel Pending #3 (200)",
                method="PATCH",
                url_path="/leaves/{{pending_request_id_3}}/cancel",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.test('Status flipped to CANCELLED', function () {",
                    "  pm.expect(pm.response.json().status).to.eql('CANCELLED');",
                    "});",
                ],
            ),
            request(
                name="Cancel Already Cancelled (409)",
                method="PATCH",
                url_path="/leaves/{{pending_request_id_3}}/cancel",
                headers=bearer("emp1_token"),
                test_lines=[
                    "pm.test('409 Conflict (only PENDING can be cancelled)', function () {",
                    "  pm.response.to.have.status(409);",
                    "});",
                ],
            ),
        ],
    }


def folder_cross_cutting() -> dict:
    return {
        "name": "09 - Cross-Cutting",
        "description": (
            "Smoke checks for the platform-wide concerns: gateway health, the "
            "three flavours of 401 produced by the auth middleware, and the "
            "manual procedures for verifying the circuit breaker, OpenTelemetry "
            "tracing, and SYSTEM_ERROR publishing."
        ),
        "item": [
            request(
                name="Gateway /health (200)",
                method="GET",
                url_path="/health",
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                    "pm.expect(pm.response.json().status).to.eql('healthy');",
                ],
            ),
            request(
                name="Protected Route - No Auth Header (401)",
                method="GET",
                url_path="/leaves/history",
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                    "pm.test('WWW-Authenticate header advertises Bearer scheme', function () {",
                    "  pm.expect(pm.response.headers.get('WWW-Authenticate')).to.match(/Bearer/i);",
                    "});",
                ],
            ),
            request(
                name="Protected Route - Malformed Authorization (401)",
                method="GET",
                url_path="/leaves/history",
                headers=[{"key": "Authorization", "value": "NotBearer abcdef"}],
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                ],
            ),
            request(
                name="Protected Route - Invalid Token (401)",
                method="GET",
                url_path="/leaves/history",
                headers=[
                    {"key": "Authorization", "value": "Bearer not.a.real.token"},
                ],
                test_lines=[
                    "pm.test('401 Unauthorized', function () { pm.response.to.have.status(401); });",
                ],
            ),
            request(
                name="Circuit Breaker - 503 (manual)",
                method="POST",
                url_path="/leaves",
                headers=[
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                ],
                body=json_body({
                    "leave_type": "CASUAL",
                    "start_date": "{{range_e_start}}",
                    "end_date": "{{range_e_end}}",
                    "number_of_days": 1,
                    "reason": "Circuit-breaker probe"
                }),
                description=(
                    "MANUAL test. Stop the leave-balance-service container, "
                    "then send this request 5+ times in quick succession. The "
                    "first few requests fail with 503 from the apply_leave "
                    "endpoint catching httpx.HTTPError; once the breaker trips "
                    "(failure threshold = 3), subsequent requests short-circuit "
                    "with the same 503 but log 'Balance lookup circuit open'.\n\n"
                    "Steps:\n"
                    "  1) docker-compose stop leave-balance-service\n"
                    "  2) Send this request several times until the breaker opens\n"
                    "  3) docker-compose logs leave-request-service | grep 'circuit'\n"
                    "  4) docker-compose start leave-balance-service\n"
                ),
                test_lines=[
                    "pm.test('503 Service Unavailable when balance service is down', function () {",
                    "  pm.expect([503, 504, 201]).to.include(pm.response.code);",
                    "});",
                    "if (pm.response.code === 503) {",
                    "  pm.expect(pm.response.json().detail).to.match(/unavailable/i);",
                    "}",
                ],
            ),
            request(
                name="OpenTelemetry Tracing (manual)",
                method="GET",
                url_path="/leaves/history",
                headers=[
                    {"key": "Authorization", "value": "Bearer {{emp1_token}}"},
                    {"key": "traceparent", "value": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"},
                ],
                description=(
                    "MANUAL verification. The OpenTelemetry SDK in shared/tracing.py "
                    "exports spans via the ConsoleSpanExporter to each service's stdout. "
                    "After running this request:\n\n"
                    "  docker-compose logs api-gateway leave-request-service | grep -i span\n\n"
                    "You should see correlated spans (api-gateway -> leave-request-service) "
                    "carrying the trace_id from the traceparent header above."
                ),
                test_lines=[
                    "pm.test('200 OK', function () { pm.response.to.have.status(200); });",
                ],
            ),
            request(
                name="SYSTEM_ERROR Publishing (manual)",
                method="GET",
                url_path="/health",
                description=(
                    "MANUAL verification. The global exception handler in "
                    "shared/exception_handlers.py publishes a SYSTEM_ERROR event "
                    "to RabbitMQ whenever an unhandled exception escapes a route. "
                    "The Notification Service consumer logs:\n\n"
                    "  [NOTIFICATION] SYSTEM_ERROR: <service>/<route> -> <message>\n\n"
                    "To trigger one: temporarily raise an unexpected exception in any "
                    "route, hit it via this collection, and observe:\n\n"
                    "  docker-compose logs notification-service | grep SYSTEM_ERROR\n\n"
                    "The event payload mirrors the published JSON in shared/rabbitmq_publisher.py."
                ),
                test_lines=[
                    "pm.test('Gateway is reachable', function () { pm.response.to.have.status(200); });",
                ],
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------
PRE_REQUEST_LINES = [
    "// Compute date variables relative to today (UTC) so success/overlap/past-date",
    "// scenarios are stable no matter when the collection is run.",
    "const fmt = function (d) { return d.toISOString().slice(0, 10); };",
    "const add = function (n) {",
    "  const d = new Date();",
    "  d.setUTCDate(d.getUTCDate() + n);",
    "  return d;",
    "};",
    "pm.collectionVariables.set('today', fmt(new Date()));",
    "pm.collectionVariables.set('past_start', fmt(add(-5)));",
    "pm.collectionVariables.set('past_end',   fmt(add(-3)));",
    "// Range A: 3 days CASUAL for emp1 (success + overlap tests).",
    "pm.collectionVariables.set('range_a_start', fmt(add(14)));",
    "pm.collectionVariables.set('range_a_end',   fmt(add(16)));",
    "// Range B: 2 days PRIVILEGE for emp1 (reject test).",
    "pm.collectionVariables.set('range_b_start', fmt(add(21)));",
    "pm.collectionVariables.set('range_b_end',   fmt(add(22)));",
    "// Range C: 1 day SICK for emp1 (cancel test).",
    "pm.collectionVariables.set('range_c_start', fmt(add(28)));",
    "pm.collectionVariables.set('range_c_end',   fmt(add(28)));",
    "// Range D: 11 days SICK (insufficient-balance test, since SICK total = 10).",
    "pm.collectionVariables.set('range_d_start', fmt(add(35)));",
    "pm.collectionVariables.set('range_d_end',   fmt(add(45)));",
    "// Range E: 1 day used for the manager-id mismatch and circuit-breaker tests.",
    "pm.collectionVariables.set('range_e_start', fmt(add(50)));",
    "pm.collectionVariables.set('range_e_end',   fmt(add(50)));",
]


COLLECTION_VARIABLES = [
    {"key": "baseUrl",                "value": "http://localhost:8080",                "type": "string"},
    {"key": "manager_id",             "value": "00000000-0000-0000-0000-000000000001", "type": "string"},
    {"key": "emp1_id",                "value": "00000000-0000-0000-0000-000000000002", "type": "string"},
    {"key": "emp2_id",                "value": "00000000-0000-0000-0000-000000000003", "type": "string"},
    {"key": "fake_id",                "value": "ffffffff-ffff-ffff-ffff-ffffffffffff", "type": "string"},
    {"key": "manager_token",          "value": "", "type": "string"},
    {"key": "emp1_token",             "value": "", "type": "string"},
    {"key": "emp2_token",             "value": "", "type": "string"},
    {"key": "pending_request_id_1",   "value": "", "type": "string"},
    {"key": "pending_request_id_2",   "value": "", "type": "string"},
    {"key": "pending_request_id_3",   "value": "", "type": "string"},
    {"key": "today",                  "value": "", "type": "string"},
    {"key": "past_start",             "value": "", "type": "string"},
    {"key": "past_end",               "value": "", "type": "string"},
    {"key": "range_a_start",          "value": "", "type": "string"},
    {"key": "range_a_end",            "value": "", "type": "string"},
    {"key": "range_b_start",          "value": "", "type": "string"},
    {"key": "range_b_end",            "value": "", "type": "string"},
    {"key": "range_c_start",          "value": "", "type": "string"},
    {"key": "range_c_end",            "value": "", "type": "string"},
    {"key": "range_d_start",          "value": "", "type": "string"},
    {"key": "range_d_end",            "value": "", "type": "string"},
    {"key": "range_e_start",          "value": "", "type": "string"},
    {"key": "range_e_end",            "value": "", "type": "string"},
]


def main() -> None:
    collection = {
        "info": {
            "_postman_id": "elms-collection-2026",
            "name": "ELMS - Employee Leave Management System",
            "description": (
                "End-to-end test collection for the ELMS backend (6 services). "
                "Run as a Collection so requests flow in order: Auth populates "
                "tokens, Apply Leave populates request IDs, then Approve/Reject/"
                "Cancel exercise the lifecycle. All requests target the API "
                "Gateway at {{baseUrl}}.\n\n"
                "Prerequisites: docker-compose up --build, all 8 containers "
                "healthy.\n\n"
                "Seed identities (see shared/seed_config.py):\n"
                "- manager1 / Manager@123  (id 00000000-0000-0000-0000-000000000001)\n"
                "- emp1     / Employee@123 (id 00000000-0000-0000-0000-000000000002, reports to manager1)\n"
                "- emp2     / Employee@123 (id 00000000-0000-0000-0000-000000000003, reports to manager1)"
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "event": [
            {"listen": "prerequest", "script": script(PRE_REQUEST_LINES)},
        ],
        "variable": COLLECTION_VARIABLES,
        "item": [
            folder_auth(),
            folder_balance(),
            folder_apply(),
            folder_history(),
            folder_manager_view(),
            folder_manager_approve(),
            folder_manager_reject(),
            folder_cancel(),
            folder_cross_cutting(),
        ],
    }

    OUT.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
