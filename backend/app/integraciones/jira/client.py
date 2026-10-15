"""Cliente mínimo de la REST API de Jira Cloud (v3 + Agile).

Autentica con email + API token (basic auth). El token nunca se loguea: los
errores llevan método, path, status y el cuerpo de la respuesta de Jira.
"""

from typing import Any

import httpx

from app.core.config import Settings, get_settings

ISSUE_FIELDS = ["summary", "status", "updated", "created", "issuetype", "assignee"]


class JiraError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def transitorio(self) -> bool:
        """Red caída, rate limit o error de Jira: vale la pena reintentar.
        Un 4xx (datos o permisos inválidos) va a fallar igual la próxima vez."""
        return self.status_code is None or self.status_code == 429 or self.status_code >= 500


class JiraClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.jira_email or not self.settings.jira_api_token:
            raise JiraError("Faltan AISEC_JIRA_EMAIL / AISEC_JIRA_API_TOKEN")
        self._http = httpx.Client(
            base_url=self.settings.jira_base_url.rstrip("/"),
            auth=(self.settings.jira_email, self.settings.jira_api_token),
            headers={"Accept": "application/json"},
            timeout=30,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise JiraError(f"{method} {path}: {type(exc).__name__}") from exc
        if resp.is_error:
            raise JiraError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}", resp.status_code)
        return resp.json() if resp.content else None

    # --- búsqueda y lectura ---

    def search_jql(self, jql: str, fields: list[str], properties: list[str] | None = None) -> list[dict]:
        issues: list[dict] = []
        token: str | None = None
        while True:
            body: dict[str, Any] = {"jql": jql, "fields": fields, "maxResults": 100}
            if properties:
                body["properties"] = properties
            if token:
                body["nextPageToken"] = token
            data = self._request("POST", "/rest/api/3/search/jql", json=body)
            issues.extend(data.get("issues", []))
            token = data.get("nextPageToken")
            if not token or data.get("isLast", True):
                return issues

    def get_comments(self, issue_key: str) -> list[dict]:
        comments: list[dict] = []
        start = 0
        while True:
            data = self._request(
                "GET",
                f"/rest/api/3/issue/{issue_key}/comment",
                params={"startAt": start, "maxResults": 100, "orderBy": "created", "expand": "properties"},
            )
            batch = data.get("comments", [])
            comments.extend(batch)
            start += len(batch)
            if not batch or start >= data.get("total", 0):
                return comments

    def get_board_configuration(self, board_id: int) -> dict:
        return self._request("GET", f"/rest/agile/1.0/board/{board_id}/configuration")

    def get_transitions(self, issue_key: str) -> list[dict]:
        return self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")["transitions"]

    def search_assignable(self, issue_key: str, query: str, limit: int = 20) -> list[dict]:
        """Usuarios a los que se puede asignar el ticket (según los permisos del proyecto)."""
        return self._request(
            "GET",
            "/rest/api/3/user/assignable/search",
            params={"issueKey": issue_key, "query": query, "maxResults": limit},
        )

    # --- escritura ---

    def assign_issue(self, issue_key: str, account_id: str | None) -> None:
        """account_id None deja el ticket sin asignar."""
        self._request("PUT", f"/rest/api/3/issue/{issue_key}/assignee", json={"accountId": account_id})

    def create_issue(self, fields: dict, properties: dict[str, Any] | None = None) -> dict:
        body: dict[str, Any] = {"fields": fields}
        if properties:
            body["properties"] = [{"key": k, "value": v} for k, v in properties.items()]
        return self._request("POST", "/rest/api/3/issue", json=body)

    def update_issue(self, issue_key: str, fields: dict) -> None:
        self._request("PUT", f"/rest/api/3/issue/{issue_key}", json={"fields": fields})

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions", json={"transition": {"id": transition_id}})

    def add_internal_comment(self, issue_key: str, body_adf: dict, properties: dict[str, Any] | None = None) -> dict:
        """Comentario interno de Service Management: sólo lo ven los agentes."""
        props = [{"key": "sd.public.comment", "value": {"internal": True}}]
        props += [{"key": k, "value": v} for k, v in (properties or {}).items()]
        return self._request(
            "POST", f"/rest/api/3/issue/{issue_key}/comment", json={"body": body_adf, "properties": props}
        )
