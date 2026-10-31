# Zlang (v0.1)

A tiny C-like language that compiles to ZX-16 assembly with `zlangc`.

```
fn fib(n) {
    if (n < 2) { return n; }
    return fib(n - 1) + fib(n - 2);
}

fn main() {
    print(fib(10));
    putc('\n');
}
```

## Language

- The only type is a 16-bit integer. Literals: `42`, `0xFF`, `'a'`, `'\n'`.
- Program = functions. Execution starts in `fn main()` (no parameters).
- Statements: `var x = expr;` `x = expr;` `if (c) { } else { }` `while (c) { }`
  `return expr;` and expression statements such as `foo(1, 2);`
- Local variables are block scoped. A function that does not `return` returns 0.
- Comments: `// ...`
- Operators, from the lowest to the highest precedence:
  `||` `&&` `|` `^` `&` `==  !=` `<  <=  >  >=` `<<  >>` `+  -` `*  /  %`;
  unary `-` and `!`. `&&` and `||` short-circuit.
- Comparisons are **signed**; `/`, `%` and `>>` are **unsigned**.

## Built-in functions

| Call | Effect |
|---|---|
| `print(x)` | print `x` as an unsigned decimal number |
| `putc(x)` | print the character with code `x` |
| `puts("text")` | print a string literal (only literals are allowed) |

## Calling convention

- The caller pushes the arguments left to right, executes `call f_NAME`, then
  removes them with `addi r7, 2*N`.
- `r0` holds the result and expression values, `r1` is scratch, `r6` is the frame
  pointer, `r7` is the stack pointer.
- Function prologue: `push r6; mov r6, r7; addi r7, -2*locals`.
  Epilogue: `mov r7, r6; pop r6; ret`.
- Parameter `i` of `n` is at `[r6 + 4 + 2*(n-1-i)]`, local number `k` (from 1)
  is at `[r6 - 2*k]`.
- Binary expressions: left value is pushed, right value goes to `r1`, left is
  popped back into `r0`.

## Not yet supported

Global variables, arrays and pointers, `break`/`continue`, `for` loops.
