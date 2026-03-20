"""Flow Converter - Nazar YAML formatini Maestro formatina cevirir ve tersini yapar."""
from pathlib import Path
from typing import Dict, List, Optional

import yaml


# Nazar -> Maestro donusum haritalari
# Nazar formati: {action: "tapOn", target: "Login"}
# Maestro formati: - tapOn: "Login" veya - tapOn: {id: "login_btn"}

NAZAR_TO_MAESTRO_ACTIONS = {
    "launchApp": "launchApp",
    "navigate": "launchApp",  # Nazar navigate -> Maestro launchApp ile acilir
    "goBack": "back",
    "scrollDown": "scroll",
    "scrollUp": "scroll",
    "tapOn": "tapOn",
    "longPress": "longPressOn",
    "doubleTap": "doubleTapOn",
    "inputText": "inputText",
    "clearText": "clearText",
    "selectOption": "tapOn",
    "assertVisible": "assertVisible",
    "assertNotVisible": "assertNotVisible",
    "assertText": "assertVisible",
    "assertEnabled": "assertVisible",
    "assertDisabled": "assertVisible",
    "waitForVisible": "waitForAnimationToEnd",
    "screenshot": "takeScreenshot",
    "wait": "waitForAnimationToEnd",
    "runFlow": "runFlow",
}

MAESTRO_TO_NAZAR_ACTIONS = {
    "launchApp": "launchApp",
    "back": "goBack",
    "scroll": "scrollDown",
    "tapOn": "tapOn",
    "longPressOn": "longPress",
    "doubleTapOn": "doubleTap",
    "inputText": "inputText",
    "clearText": "clearText",
    "assertVisible": "assertVisible",
    "assertNotVisible": "assertNotVisible",
    "waitForAnimationToEnd": "waitForVisible",
    "takeScreenshot": "screenshot",
    "runFlow": "runFlow",
    "swipe": "scrollDown",
    "inputRandomText": "inputText",
    "inputRandomNumber": "inputText",
    "inputRandomEmail": "inputText",
    "inputRandomPersonName": "inputText",
    "openLink": "navigate",
    "pressKey": "tapOn",
    "eraseText": "clearText",
    "hideKeyboard": "wait",
    "evalScript": "wait",
    "copyTextFrom": "assertVisible",
    "repeat": "wait",
}


def _convert_nazar_step_to_maestro(step: Dict) -> Optional[Dict]:
    """Tek bir Nazar adimini Maestro formatina cevir.

    Nazar formati:
        action: tapOn
        target: "Login"
        value: "test@mail.com"  (inputText icin)

    Maestro formati:
        - tapOn: "Login"
        - inputText: "test@mail.com"  (hedefi ayri satirda)
    """
    action = step.get("action", "")
    target = step.get("target", "")
    value = step.get("value", "")
    maestro_action = NAZAR_TO_MAESTRO_ACTIONS.get(action)

    if not maestro_action:
        return None

    # launchApp
    if action == "launchApp":
        app_id = target or step.get("appId", "")
        if app_id:
            return {"launchApp": {"appId": app_id}}
        return {"launchApp": True}

    # navigate -> Maestro'da launchApp veya openLink
    if action == "navigate":
        return {"launchApp": {"appId": target}}

    # goBack
    if action == "goBack":
        return {"back": True}

    # scroll
    if action == "scrollDown":
        return {"scroll": True}
    if action == "scrollUp":
        return {"scroll": {"direction": "UP"}}

    # tapOn
    if action == "tapOn":
        if _looks_like_id(target):
            return {"tapOn": {"id": target}}
        return {"tapOn": target}

    # longPress
    if action == "longPress":
        if _looks_like_id(target):
            return {"longPressOn": {"id": target}}
        return {"longPressOn": target}

    # doubleTap
    if action == "doubleTap":
        if _looks_like_id(target):
            return {"doubleTapOn": {"id": target}}
        return {"doubleTapOn": target}

    # inputText
    if action == "inputText":
        result = {"inputText": value or ""}
        if target:
            if _looks_like_id(target):
                return {"tapOn": {"id": target}, "_next": result}
            return {"tapOn": target, "_next": result}
        return result

    # clearText
    if action == "clearText":
        if target:
            if _looks_like_id(target):
                return {"tapOn": {"id": target}, "_next": {"eraseText": 100}}
            return {"tapOn": target, "_next": {"eraseText": 100}}
        return {"eraseText": 100}

    # selectOption -> tapOn ile
    if action == "selectOption":
        steps = []
        if target:
            steps.append({"tapOn": target})
        if value:
            steps.append({"tapOn": value})
        return steps[0] if len(steps) == 1 else {"_multi": steps}

    # assertVisible
    if action == "assertVisible":
        if _looks_like_id(target):
            return {"assertVisible": {"id": target}}
        return {"assertVisible": target}

    # assertNotVisible
    if action == "assertNotVisible":
        if _looks_like_id(target):
            return {"assertNotVisible": {"id": target}}
        return {"assertNotVisible": target}

    # assertText -> assertVisible + icerik kontrolu
    if action == "assertText":
        if value:
            return {"assertVisible": value}
        return {"assertVisible": target}

    # assertEnabled / assertDisabled -> assertVisible olarak
    if action in ("assertEnabled", "assertDisabled"):
        if _looks_like_id(target):
            return {"assertVisible": {"id": target}}
        return {"assertVisible": target}

    # waitForVisible
    if action == "waitForVisible":
        timeout = step.get("timeout", 5000)
        if _looks_like_id(target):
            return {"assertVisible": {"id": target, "timeout": timeout}}
        return {"assertVisible": {"text": target, "timeout": timeout}}

    # screenshot
    if action == "screenshot":
        name = target or "screenshot"
        return {"takeScreenshot": name}

    # wait
    if action == "wait":
        duration = step.get("duration", 1000)
        return {"waitForAnimationToEnd": {"timeout": duration}}

    # runFlow
    if action == "runFlow":
        flow = step.get("flow", target)
        return {"runFlow": flow}

    return None


def _convert_maestro_step_to_nazar(step: Dict) -> Optional[Dict]:
    """Tek bir Maestro adimini Nazar formatina cevir."""
    if not isinstance(step, dict):
        return None

    for maestro_action, content in step.items():
        nazar_action = MAESTRO_TO_NAZAR_ACTIONS.get(maestro_action)
        if not nazar_action:
            continue

        result = {"action": nazar_action}

        # launchApp
        if maestro_action == "launchApp":
            if isinstance(content, dict):
                result["target"] = content.get("appId", "")
            elif isinstance(content, str):
                result["target"] = content
            return result

        # back
        if maestro_action == "back":
            return result

        # scroll
        if maestro_action == "scroll":
            if isinstance(content, dict):
                direction = content.get("direction", "DOWN")
                if direction.upper() == "UP":
                    result["action"] = "scrollUp"
            return result

        # tapOn, longPressOn, doubleTapOn
        if maestro_action in ("tapOn", "longPressOn", "doubleTapOn"):
            if isinstance(content, dict):
                result["target"] = (
                    content.get("id")
                    or content.get("text")
                    or content.get("label", "")
                )
            elif isinstance(content, str):
                result["target"] = content
            return result

        # inputText
        if maestro_action == "inputText":
            if isinstance(content, str):
                result["value"] = content
            elif isinstance(content, dict):
                result["value"] = content.get("text", "")
                result["target"] = content.get("id", "")
            return result

        # clearText / eraseText
        if maestro_action in ("clearText", "eraseText"):
            if isinstance(content, dict):
                result["target"] = content.get("id", "")
            return result

        # assertVisible, assertNotVisible
        if maestro_action in ("assertVisible", "assertNotVisible"):
            if isinstance(content, dict):
                result["target"] = (
                    content.get("text")
                    or content.get("id")
                    or content.get("label", "")
                )
            elif isinstance(content, str):
                result["target"] = content
            return result

        # takeScreenshot
        if maestro_action == "takeScreenshot":
            if isinstance(content, str):
                result["target"] = content
            return result

        # waitForAnimationToEnd
        if maestro_action == "waitForAnimationToEnd":
            if isinstance(content, dict):
                result["duration"] = content.get("timeout", 1000)
            else:
                result["duration"] = 1000
            return result

        # runFlow
        if maestro_action == "runFlow":
            if isinstance(content, str):
                result["flow"] = content
            elif isinstance(content, dict):
                result["flow"] = content.get("file", "")
            return result

        # Bilinmeyen aksiyonlar icin genel donusum
        if isinstance(content, str):
            result["target"] = content
        elif isinstance(content, dict):
            result["target"] = (
                content.get("id")
                or content.get("text")
                or str(content)
            )
        return result

    return None


def _looks_like_id(target: str) -> bool:
    """Hedefin bir element ID'si mi yoksa gorunen metin mi oldugunu tahmin et."""
    if not target:
        return False
    # Bosluk iceriyorsa buyuk ihtimal gorunen metin
    if " " in target:
        return False
    # snake_case veya camelCase ise buyuk ihtimal ID
    if "_" in target:
        return True
    if target[0].islower() and any(c.isupper() for c in target[1:]):
        return True
    # Sadece kucuk harflerden olusuyorsa ID olabilir
    if target.isidentifier() and target.islower() and len(target) > 2:
        return True
    return False


def convert_nazar_to_maestro(nazar_yaml_path: str, project_path: str = None) -> str:
    """Nazar YAML dosyasini Maestro formatina cevir.

    Args:
        nazar_yaml_path: Nazar formatindaki YAML dosyasinin yolu.
        project_path: Proje kok dizini (opsiyonel). Verilirse YAML dosyasinin
                      bu dizin icinde oldugu dogrulanir.

    Returns:
        Maestro YAML icerigi (str).

    Raises:
        ValueError: YAML dosyasi proje dizini disindaysa veya gecersizse.
        FileNotFoundError: YAML dosyasi bulunamazsa.
    """
    path = Path(nazar_yaml_path).resolve()

    if not path.exists():
        raise FileNotFoundError(
            "YAML dosyasi bulunamadi: {}".format(path)
        )

    # Proje dizini verildiyse, YAML dosyasinin proje icinde oldugunu dogrula
    if project_path is not None:
        resolved_project = Path(project_path).resolve()
        try:
            path.relative_to(resolved_project)
        except ValueError:
            raise ValueError(
                "YAML dosyasi proje dizini disinda: {} (proje: {})".format(
                    path, resolved_project
                )
            )

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "steps" not in data:
        raise ValueError(
            "Gecersiz Nazar YAML: 'steps' alani bulunamadi"
        )

    # Maestro meta bilgileri
    maestro_steps = []

    # appId varsa ilk adim olarak launchApp ekle
    app_id = data.get("appId")
    if app_id:
        maestro_steps.append({"launchApp": {"appId": app_id}})

    # Adimlari cevir
    for step in data.get("steps", []):
        if not isinstance(step, dict):
            continue

        converted = _convert_nazar_step_to_maestro(step)
        if converted is None:
            # Yorum olarak ekle
            maestro_steps.append(
                {"_comment": "Cevirilemeyen adim: {}".format(step)}
            )
            continue

        # Multi-step donusum (_next veya _multi)
        if "_next" in converted:
            next_step = converted.pop("_next")
            maestro_steps.append(converted)
            maestro_steps.append(next_step)
        elif "_multi" in converted:
            for sub in converted["_multi"]:
                maestro_steps.append(sub)
        else:
            maestro_steps.append(converted)

    # Yorumlari temizle, _comment satirlarini kaldir
    clean_steps = []
    for s in maestro_steps:
        if "_comment" in s:
            continue
        clean_steps.append(s)

    # Maestro YAML olustur
    output_lines = []

    # Nazar meta bilgilerini Maestro yorumu olarak ekle
    name = data.get("name", "")
    if name:
        output_lines.append("# {}".format(name))
    desc = data.get("description", "")
    if desc:
        output_lines.append("# {}".format(desc))
    if name or desc:
        output_lines.append("")

    # appId'yi ust seviyeye yaz
    if app_id:
        output_lines.append("appId: {}".format(app_id))
        output_lines.append("---")

    # Adimlari YAML olarak yaz
    yaml_content = yaml.dump(
        clean_steps,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    output_lines.append(yaml_content)
    return "\n".join(output_lines)


def convert_maestro_to_nazar(maestro_yaml_path: str, project_path: str = None) -> str:
    """Maestro YAML dosyasini Nazar formatina cevir.

    Args:
        maestro_yaml_path: Maestro formatindaki YAML dosyasinin yolu.
        project_path: Proje kok dizini (opsiyonel). Verilirse YAML dosyasinin
                      bu dizin icinde oldugu dogrulanir.

    Returns:
        Nazar YAML icerigi (str).

    Raises:
        ValueError: YAML dosyasi proje dizini disindaysa.
        FileNotFoundError: YAML dosyasi bulunamazsa.
    """
    path = Path(maestro_yaml_path).resolve()

    if not path.exists():
        raise FileNotFoundError(
            "YAML dosyasi bulunamadi: {}".format(path)
        )

    # Proje dizini verildiyse, YAML dosyasinin proje icinde oldugunu dogrula
    if project_path is not None:
        resolved_project = Path(project_path).resolve()
        try:
            path.relative_to(resolved_project)
        except ValueError:
            raise ValueError(
                "YAML dosyasi proje dizini disinda: {} (proje: {})".format(
                    path, resolved_project
                )
            )

    content = path.read_text(encoding="utf-8")

    # Maestro dosyasi birden fazla YAML dokumani icerebilir (--- ayiricisi)
    documents = list(yaml.safe_load_all(content))

    # Meta bilgileri ilk dokumandan al
    meta = {}
    steps_data = []

    for doc in documents:
        if doc is None:
            continue
        if isinstance(doc, dict):
            # Meta bilgi dokumani (appId vs.)
            if "appId" in doc:
                meta["appId"] = doc["appId"]
            if "name" in doc:
                meta["name"] = doc["name"]
        elif isinstance(doc, list):
            # Adimlar
            steps_data = doc

    # Eger tek dokumanli ve liste ise
    if not steps_data and documents:
        first = documents[0]
        if isinstance(first, list):
            steps_data = first
        elif isinstance(first, dict) and "appId" not in first:
            # Tek adimlik dosya olabilir
            steps_data = [first]

    # Nazar adimlarina cevir
    nazar_steps = []
    for step in steps_data:
        converted = _convert_maestro_step_to_nazar(step)
        if converted:
            nazar_steps.append(converted)

    # Nazar YAML olustur
    nazar_data = {
        "apiVersion": "nazar/v1",
        "name": meta.get("name", path.stem.replace("-", " ").title() + " Testi"),
        "description": "Maestro'dan donusturulmus test",
        "platform": "all",
        "priority": "high",
    }

    if meta.get("appId"):
        nazar_data["appId"] = meta["appId"]

    nazar_data["steps"] = nazar_steps

    return yaml.dump(
        nazar_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
