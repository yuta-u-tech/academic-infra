"""toeic_forms.client.resolve_question_ids（Forms APIはモック）。

itemId（こちらで指定した識別子）と questionId（Formsが別途発行し、
responses.list() の回答キーになる識別子）は別物であることを実APIで確認済み
（docs/2026-08-09-toeic-forms-integration.md 参照）。この関数はその対応を
forms.get() から引く。
"""

from toeic_forms.client import resolve_question_ids


class _FakeExecutable:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeFormsResource:
    def __init__(self, result):
        self._result = result

    def get(self, formId):  # noqa: N803 - googleapiclient のキーワード名に合わせる
        return _FakeExecutable(self._result)


class _FakeService:
    def __init__(self, result):
        self._forms = _FakeFormsResource(result)

    def forms(self):
        return self._forms


def test_resolve_question_ids_maps_only_requested_item_ids():
    service = _FakeService(
        {
            "items": [
                {
                    "itemId": "71b88eef",
                    "questionItem": {"question": {"questionId": "38127e67"}},
                },
                {
                    "itemId": "00000001",
                    "questionItem": {"question": {"questionId": "aaaaaaaa"}},
                },
            ]
        }
    )

    mapping = resolve_question_ids(service, "form-1", {"71b88eef"})

    assert mapping == {"71b88eef": "38127e67"}


def test_resolve_question_ids_skips_non_question_items():
    service = _FakeService({"items": [{"itemId": "71b88eef", "pageBreakItem": {}}]})

    mapping = resolve_question_ids(service, "form-1", {"71b88eef"})

    assert mapping == {}
