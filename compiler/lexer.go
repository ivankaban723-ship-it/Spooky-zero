package main

import (
	"fmt"
	"strconv"
	"strings"
)

type TokKind int

const (
	TEOF TokKind = iota
	TNum
	TIdent
	TKeyword
	TString
	TPunct
)

// Token is one lexical element. Text holds the identifier, keyword or operator
// text (or the decoded contents of a string literal); Num holds numbers and
// character literals.
type Token struct {
	Kind TokKind
	Text string
	Num  int
	Line int
}

var keywords = map[string]bool{
	"fn": true, "var": true, "if": true, "else": true, "while": true, "return": true,
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }
func isHex(c byte) bool {
	return isDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}
func isAlpha(c byte) bool {
	return c == '_' || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
}

func unescape(c byte) (byte, bool) {
	switch c {
	case 'n':
		return '\n', true
	case 't':
		return '\t', true
	case 'r':
		return '\r', true
	case '0':
		return 0, true
	case '\\':
		return '\\', true
	case '\'':
		return '\'', true
	case '"':
		return '"', true
	}
	return 0, false
}

// Lex turns source text into tokens. The last token is always TEOF.
func Lex(src string) ([]Token, error) {
	var toks []Token
	line := 1
	i, n := 0, len(src)

	for i < n {
		c := src[i]
		switch {
		case c == '\n':
			line++
			i++

		case c == ' ' || c == '\t' || c == '\r':
			i++

		case c == '/' && i+1 < n && src[i+1] == '/':
			for i < n && src[i] != '\n' {
				i++
			}

		case isDigit(c):
			start := i
			isHexNum := c == '0' && i+1 < n && (src[i+1] == 'x' || src[i+1] == 'X')
			if isHexNum {
				i += 2
				for i < n && isHex(src[i]) {
					i++
				}
			} else {
				for i < n && isDigit(src[i]) {
					i++
				}
			}
			text := src[start:i]
			var v int64
			var err error
			if isHexNum {
				v, err = strconv.ParseInt(text[2:], 16, 32)
			} else {
				v, err = strconv.ParseInt(text, 10, 32)
			}
			if err != nil || v > 65535 {
				return nil, fmt.Errorf("line %d: bad number %q (must fit in 16 bits)", line, text)
			}
			toks = append(toks, Token{Kind: TNum, Num: int(v), Line: line})

		case isAlpha(c):
			start := i
			for i < n && (isAlpha(src[i]) || isDigit(src[i])) {
				i++
			}
			word := src[start:i]
			kind := TIdent
			if keywords[word] {
				kind = TKeyword
			}
			toks = append(toks, Token{Kind: kind, Text: word, Line: line})

		case c == '\'':
			i++
			if i >= n {
				return nil, fmt.Errorf("line %d: unterminated character literal", line)
			}
			ch := src[i]
			if ch == '\\' {
				i++
				if i >= n {
					return nil, fmt.Errorf("line %d: unterminated character literal", line)
				}
				e, ok := unescape(src[i])
				if !ok {
					return nil, fmt.Errorf("line %d: bad escape sequence", line)
				}
				ch = e
			}
			i++
			if i >= n || src[i] != '\'' {
				return nil, fmt.Errorf("line %d: bad character literal", line)
			}
			i++
			toks = append(toks, Token{Kind: TNum, Num: int(ch), Line: line})

		case c == '"':
			i++
			var sb strings.Builder
			for {
				if i >= n || src[i] == '\n' {
					return nil, fmt.Errorf("line %d: unterminated string", line)
				}
				ch := src[i]
				if ch == '"' {
					i++
					break
				}
				if ch == '\\' {
					i++
					if i >= n {
						return nil, fmt.Errorf("line %d: unterminated string", line)
					}
					e, ok := unescape(src[i])
					if !ok {
						return nil, fmt.Errorf("line %d: bad escape sequence", line)
					}
					ch = e
				}
				sb.WriteByte(ch)
				i++
			}
			toks = append(toks, Token{Kind: TString, Text: sb.String(), Line: line})

		default:
			if i+1 < n {
				two := src[i : i+2]
				switch two {
				case "==", "!=", "<=", ">=", "&&", "||", "<<", ">>":
					toks = append(toks, Token{Kind: TPunct, Text: two, Line: line})
					i += 2
					continue
				}
			}
			if strings.IndexByte("+-*/%&|^<>=!(){},;", c) >= 0 {
				toks = append(toks, Token{Kind: TPunct, Text: string(c), Line: line})
				i++
				continue
			}
			return nil, fmt.Errorf("line %d: unexpected character %q", line, c)
		}
	}

	toks = append(toks, Token{Kind: TEOF, Line: line})
	return toks, nil
}
