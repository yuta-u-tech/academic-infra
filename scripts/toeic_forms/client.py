"""Forms API / Drive API 呼び出し（ネットワークを伴う薄いラッパー）。

組み立て済みの batchUpdate リクエスト（builder.py）を実際に送るだけで、
リクエスト内容の妥当性はテストしやすいよう builder.py 側に寄せてある。
"""
from __future__ import annotations


def create_form(forms_service, title: str) -> tuple[str, str]:
    """空のFormを作り、(formId, responderUri) を返す。

    forms.create は info.title のみ受け付ける（documentTitle 等は後から
    別リクエストで変える必要がある）。responderUri（回答用の公開URL）は
    formId から機械的に組み立てられる文字列ではない（Google が別に発行する、
    "1FAIpQLS..." で始まる別IDを使う）。実APIで確認済み — 必ず create()/get()
    のレスポンスからそのまま読むこと。
    """
    result = forms_service.forms().create(body={"info": {"title": title}}).execute()
    return result["formId"], result["responderUri"]


def apply_requests(forms_service, form_id: str, requests: list[dict]) -> None:
    if not requests:
        return
    forms_service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()


def resolve_question_ids(forms_service, form_id: str, item_ids: set[str]) -> dict[str, str]:
    """createItem で指定した itemId → 実際の questionId を引く。

    Forms API は itemId とは別に questionId を内部で発行し、responses.list() の
    回答は questionId をキーに返す（itemId では引けない）。実APIで確認済み。
    forms.get() で全アイテムを読み、質問アイテムだけ questionId を拾う。
    """
    form = forms_service.forms().get(formId=form_id).execute()
    mapping: dict[str, str] = {}
    for item in form.get("items", []):
        item_id = item.get("itemId")
        if item_id not in item_ids:
            continue
        question_id = item.get("questionItem", {}).get("question", {}).get("questionId")
        if question_id:
            mapping[item_id] = question_id
    return mapping


def list_responses(forms_service, form_id: str) -> list[dict]:
    """Formへの回答を全件取る（ページングを吸収する）。"""
    responses: list[dict] = []
    page_token = None
    while True:
        result = (
            forms_service.forms()
            .responses()
            .list(formId=form_id, pageToken=page_token)
            .execute()
        )
        responses.extend(result.get("responses", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return responses


def edit_url(form_id: str) -> str:
    return f"https://docs.google.com/forms/d/{form_id}/edit"


def grant_editor_access(drive_service, form_id: str, editor_emails: list[str]) -> None:
    """指定アカウントにFormのeditor権限を付与する。

    restrict_access が付与するreader権限（回答用）とは別物。Forms APIの
    `forms.responses.list()` はeditor権限を持つアカウントでないと呼べないため、
    「作った人以外がrecordを実行できるようにする」にはこちらが必要。
    """
    for email in editor_emails:
        drive_service.permissions().create(
            fileId=form_id,
            body={"type": "user", "role": "writer", "emailAddress": email},
            sendNotificationEmail=False,
        ).execute()


def restrict_access(drive_service, form_id: str, allowed_emails: list[str]) -> None:
    """特定のGoogleアカウントのみ回答可にする。

    Form は API 作成直後は所有者以外アクセス不可（非公開）なので、ここでは
    「許可した知人にreader権限を明示的に付与する」だけでよい —
    「anyone with the link」等の広い共有には決してしない。
    """
    for email in allowed_emails:
        drive_service.permissions().create(
            fileId=form_id,
            body={"type": "user", "role": "reader", "emailAddress": email},
            sendNotificationEmail=False,
        ).execute()
