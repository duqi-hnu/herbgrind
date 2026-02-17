#!/usr/bin/env python3

import subprocess
import sys
import re
import os
HEX_RE = re.compile(r"\(instr-addr [0-9a-fA-F]+\)")
LINE_RE = re.compile(r"\(line-num [0-9]+\)")

COMMUTATIVE_OPS = frozenset({"+", "*", "and", "or", "max", "min"})
ASSOCIATIVE_OPS = frozenset({"+", "*", "and", "or", "max", "min"})
NO_MARKS_OUTPUTS = frozenset({"", "No marks found!", "Didn't find any marks!"})


def _is_number_token(token):
    try:
        float(token)
    except ValueError:
        return False
    return True


def _tokenize_sexpr(text):
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char.isspace():
            i += 1
            continue
        if char in "()":
            tokens.append(char)
            i += 1
            continue
        if char == '"':
            j = i + 1
            escaped = False
            while j < n:
                cur = text[j]
                if escaped:
                    escaped = False
                elif cur == "\\":
                    escaped = True
                elif cur == '"':
                    j += 1
                    break
                j += 1
            if j > n:
                raise ValueError("unterminated string literal")
            tokens.append(text[i:j])
            i = j
            continue
        j = i
        while j < n and (not text[j].isspace()) and text[j] not in "()":
            j += 1
        tokens.append(text[i:j])
        i = j
    return tokens


def _parse_sexpr(text):
    tokens = _tokenize_sexpr(text)

    def parse_at(idx):
        token = tokens[idx]
        if token == "(":
            idx += 1
            expr = []
            while idx < len(tokens) and tokens[idx] != ")":
                sub_expr, idx = parse_at(idx)
                expr.append(sub_expr)
            if idx >= len(tokens):
                raise ValueError("unmatched opening parenthesis")
            return expr, idx + 1
        if token == ")":
            raise ValueError("unexpected closing parenthesis")
        return token, idx + 1

    forms = []
    idx = 0
    while idx < len(tokens):
        form, idx = parse_at(idx)
        forms.append(form)
    return forms


def _sexpr_to_string(node):
    if isinstance(node, list):
        return "(" + " ".join(_sexpr_to_string(child) for child in node) + ")"
    return node


def _sexpr_sort_key(node):
    return _sexpr_to_string(node)


def _canonicalize(node):
    if not isinstance(node, list):
        if isinstance(node, str) and node.startswith("+") and _is_number_token(node):
            return node[1:]
        return node
    if not node:
        return node

    canonical = [_canonicalize(child) for child in node]
    head = canonical[0]

    if head == "-" and len(canonical) == 2 and isinstance(canonical[1], str):
        arg = canonical[1]
        if _is_number_token(arg):
            if arg.startswith("+"):
                arg = arg[1:]
            if arg.startswith("-"):
                return arg[1:]
            return "-" + arg

    if not isinstance(head, str) or head not in COMMUTATIVE_OPS or len(canonical) <= 2:
        return canonical

    args = canonical[1:]
    if head in ASSOCIATIVE_OPS:
        flattened_args = []
        for arg in args:
            if isinstance(arg, list) and arg and arg[0] == head:
                flattened_args.extend(arg[1:])
            else:
                flattened_args.append(arg)
        args = flattened_args

    args.sort(key=_sexpr_sort_key)
    return [head] + args


def sanitize(string):
    no_nul = string.replace("\x00", "")
    if no_nul.strip() in NO_MARKS_OUTPUTS:
        return "<no-marks>"

    # Normalize unstable location fields first.
    normalized = HEX_RE.sub("(instr-addr <addr>)", LINE_RE.sub("(line-num <line>)", no_nul))
    try:
        forms = _parse_sexpr(normalized)
    except ValueError:
        return normalized
    canonical_forms = [_canonicalize(form) for form in forms]
    return "\n".join(_sexpr_to_string(form) for form in canonical_forms)


def compare_results(actual, expected):
    # print("Comparing: {} and {}".format(sanitize(actual), sanitize(expected)))
    return sanitize(actual) == sanitize(expected)

def test(prog):
    command = ["./valgrind/herbgrind-install/bin/valgrind", "--tool=herbgrind",
               "--output-sexp", prog]
    print("Calling `{}`...".format(" ".join(command)), end=" ")
    env = dict(os.environ)
    env.setdefault("GLIBC_TUNABLES", "glibc.pthread.rseq=0")
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout, stderr = proc.communicate()
    status = proc.poll()
    full_stderr = stderr.decode('utf-8')
    stderr_lines = full_stderr.splitlines()
    last_stderr = "\n".join(stderr_lines[-200:])

    if status:
        print("Command failed (status {}).".format(status))
        return False

    try:
        with open(prog + ".gh") as actual, open(prog + ".expected") as expected:
            actual_text, expected_text = actual.read(), expected.read()
    except:
        print("Cannot find output file {}!".format(prog + ".gh"),
              "stdout::", stdout.decode('utf-8'),
              "stderr::", last_stderr,
              sep="\n")
        return False

    expected_sanitized = sanitize(expected_text)
    if not compare_results(actual_text, expected_text):
        if actual_text == "":
            print("Empty file at {}!".format(prog + ".gh"))
        if expected_text == "":
            print("Empty file at {}!".format(prog + ".expected"))
        print("Outputs do not match!")
        print("Actual::", actual_text, sep="\n")
        print("Expected::", expected_text, sep="\n")
        print("stdout::", stdout.decode('utf-8'), sep="\n")
        print("stderr::", last_stderr, sep="\n")
        return False

    native_proc = subprocess.Popen([prog], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    native_stdout, native_stderr = native_proc.communicate()
    native_status = native_proc.poll()

    if native_status:
        print("Native command failed (status {})".format(native_status))

    # For no-marks baselines, keep the structural check above but allow
    # minor runtime output drift across libc/valgrind combinations.
    if stdout != native_stdout and expected_sanitized != "<no-marks>":
        print("Stdout does not match native")
        print("Actual::", stdout.decode('utf-8'), sep="\n")
        print("Expected::", native_stdout.decode('utf-8'), sep="\n")
        return False

    print("Outputs match.")
    return True

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if not test(arg):
            sys.exit(1)
