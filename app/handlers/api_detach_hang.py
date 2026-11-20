from app.handlers.base import BaseHandler
from app.services.detach_hang_ledger import append_ledger, dashboard
from app.services.detach_hang_surface import reconcile_surface, snapshot


class ApiDetachHangDash(BaseHandler):
    def get(self):
        self.require_user()
        self.json(dashboard())


class ApiDetachHangNote(BaseHandler):
    def post(self):
        self.require_user()
        body = self.read_json()
        self.json(
            append_ledger(
                int(body.get("plan_id") or 0),
                str(body.get("note") or "退挂悬挂"),
            )
        )


class ApiDetachHangHalf(BaseHandler):
    def post(self):
        self.require_user()
        self.json(reconcile_surface())


class ApiDetachHangSnap(BaseHandler):
    def get(self):
        self.require_user()
        self.json(snapshot())
