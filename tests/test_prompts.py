from brain.prompts import (
    ASSISTANT_DE,
    ASSISTANT_DE_TEMPLATE,
    ASSISTANT_EN,
    INTERPRETER_SYS,
    system_for,
)


def test_interpreter_mode():
    s = system_for("interpreter", is_owner=True, lang="de")
    assert s is INTERPRETER_SYS


def test_assistant_de_renders_contacts():
    contacts = [
        {"name": "Testcall", "aliases": ["testcall", "test call"]},
        {"name": "IRS (US)", "aliases": ["IRS", "Finanzamt USA"]},
    ]
    s = system_for("assistant", is_owner=True, lang="de", contacts=contacts)
    assert "Testcall" in s
    assert "test call" in s
    assert "IRS" in s
    assert "dial_contact" in s


def test_assistant_de_no_contacts_gracefully():
    s = system_for("assistant", is_owner=True, lang="de")
    assert "dial_contact" in s


def test_assistant_en():
    s = system_for("assistant", is_owner=True, lang="en")
    assert s is ASSISTANT_EN


def test_prompts_mention_tools():
    assert "dial_contact" in ASSISTANT_DE_TEMPLATE
    assert "dial_contact" in ASSISTANT_EN
    assert "hang up" in INTERPRETER_SYS.lower() or "tool" in INTERPRETER_SYS.lower()
