"""Изолированный тест разбора JSON из ответа LLM — без обращения к модели."""
import llm


def test_plain_array():
    assert llm.extract_json('[{"a":1},{"a":2}]') == [{"a": 1}, {"a": 2}]


def test_fenced_json():
    text = "Вот результат:\n```json\n{\"price\": 1500}\n```\nготово"
    assert llm.extract_json(text) == {"price": 1500}


def test_strips_think_block():
    text = "<think>надо подумать</think>\n[1, 2, 3]"
    assert llm.extract_json(text) == [1, 2, 3]


def test_embedded_object_with_noise():
    text = 'Ответ: {"name": "Бумага", "qty": 5} — всё.'
    assert llm.extract_json(text) == {"name": "Бумага", "qty": 5}


def test_raises_on_garbage():
    import pytest

    with pytest.raises(ValueError):
        llm.extract_json("нет здесь никакого json")
