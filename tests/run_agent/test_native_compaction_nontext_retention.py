"""Image-only user content across native Codex compaction checkpoints."""

from agent.codex_responses_adapter import _chat_messages_to_responses_input
from agent.native_compaction import _extract_item_text, prune_pre_checkpoint_items


_IMAGE_URL = "data:image/png;base64,AAAA"
_CHAT_IMAGE_PART = {"type": "image_url", "image_url": {"url": _IMAGE_URL}}
_RESPONSES_IMAGE_PART = {"type": "input_image", "image_url": _IMAGE_URL}
_CHECKPOINT = {"type": "compaction", "encrypted_content": "blob_cp"}


def test_extract_item_text_remains_text_only_for_image_content():
    assert _extract_item_text({"content": [_RESPONSES_IMAGE_PART]}) is None


def test_valid_image_only_user_message_is_retained_verbatim():
    image_only = {"role": "user", "content": [_RESPONSES_IMAGE_PART]}

    pruned = prune_pre_checkpoint_items(
        [image_only, _CHECKPOINT, {"role": "user", "content": "after"}],
        retained_user_token_budget=1,
    )

    assert pruned == [
        _CHECKPOINT,
        image_only,
        {"role": "user", "content": "after"},
    ]
    assert pruned[1] is image_only


def test_image_retention_obeys_budget_and_rejects_malformed_parts():
    valid = {"role": "user", "content": [_RESPONSES_IMAGE_PART]}
    assert prune_pre_checkpoint_items(
        [valid, _CHECKPOINT], retained_user_token_budget=0
    ) == [_CHECKPOINT]

    for content in (
        [{}],
        [{"type": "input_image", "image_url": ""}],
        [{"type": "unknown", "value": "not an attachment"}],
    ):
        malformed = {"role": "user", "content": content}
        assert prune_pre_checkpoint_items(
            [malformed, _CHECKPOINT], retained_user_token_budget=1
        ) == [_CHECKPOINT]


def test_adapter_preserves_image_only_user_message_across_checkpoint():
    converted = _chat_messages_to_responses_input(
        [
            {"role": "user", "content": [_CHAT_IMAGE_PART]},
            {
                "role": "assistant",
                "content": "checkpoint turn",
                "codex_reasoning_items": [_CHECKPOINT],
            },
            {"role": "user", "content": "after checkpoint"},
        ],
        native_compaction_eligible=True,
    )

    assert converted == [
        _CHECKPOINT,
        {"role": "user", "content": [_RESPONSES_IMAGE_PART]},
        {"role": "assistant", "content": "checkpoint turn"},
        {"role": "user", "content": "after checkpoint"},
    ]
