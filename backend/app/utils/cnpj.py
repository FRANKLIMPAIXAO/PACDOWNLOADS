import re


def normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def validate_cnpj(value: str) -> bool:
    cnpj = normalize_cnpj(value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def calculate_digit(base: str) -> str:
        if len(base) == 12:
            weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        else:
            weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        total = sum(int(digit) * weight for digit, weight in zip(base, weights))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first_digit = calculate_digit(cnpj[:12])
    second_digit = calculate_digit(cnpj[:12] + first_digit)
    return cnpj[-2:] == first_digit + second_digit
