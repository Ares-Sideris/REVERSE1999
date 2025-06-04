# dat_decrypt.py
def find_xor_key(data: bytes, signature: bytes = b"UnityFS") -> int | None:
    """
    Пробуем все 0–255, возвращаем ключ, при котором первые len(signature)
    байт после XOR совпадают с signature.
    """
    for k in range(256):
        if all((data[i] ^ k) == signature[i] for i in range(len(signature))):
            return k
    return None

def decrypt_dat(input_path: str, output_path: str) -> bool:
    """
    Дешифрует файл input_path одно-байтовым XOR, сохраняет в output_path.
    Возвращает True, если ключ найден и файл записан, иначе False.
    """
    with open(input_path, "rb") as f:
        raw = f.read()
    key = find_xor_key(raw)
    if key is None:
        return False
    dec = bytes(b ^ key for b in raw)
    with open(output_path, "wb") as f:
        f.write(dec)
    return True