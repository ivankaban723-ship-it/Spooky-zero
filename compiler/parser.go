package main

import "fmt"

// ---- errors ----

type compileError struct{ msg string }

// fail aborts compilation with a message; it is caught by recoverError.
func fail(line int, format string, args ...interface{}) {
	panic(compileError{fmt.Sprintf("line %d: ", line) + fmt.Sprintf(format, args...)})
}

func recoverError(err *error) {
	if r := recover(); r != nil {
		if ce, ok := r.(compileError); ok {
			*err = fmt.Errorf("%s", ce.msg)
			return
		}
		panic(r)
	}
}

// ---- AST ----

type Expr interface{}

type NumExpr struct{ Val int }
type StrExpr struct {
	Val  string
	Line int
}
type VarExpr struct {
	Name string
	Line int
}
type UnaryExpr struct {
	Op string
	X  Expr
}
type BinaryExpr struct {
	Op   string
	L, R Expr
}
type CallExpr struct {
	Name string
	Args []Expr
	Line int
}

type Stmt interface{}

type VarStmt struct {
	Name string
	Init Expr
	Line int
}
type AssignStmt struct {
	Name string
	Val  Expr
	Line int
}
type IfStmt struct {
	Cond Expr
	Then []Stmt
	Else []Stmt
}
type WhileStmt struct {
	Cond Expr
	Body []Stmt
}
type ReturnStmt struct{ Val Expr }
type ExprStmt struct{ X Expr }

type Func struct {
	Name   string
	Params []string
	Body   []Stmt
	Line   int
}

// Const is a top-level named number: const NAME = 42;
type Const struct {
	Name string
	Val  int
	Line int
}

// ---- parser ----

type Parser struct {
	toks []Token
	pos  int
}

func describe(t Token) string {
	switch t.Kind {
	case TEOF:
		return "end of file"
	case TNum:
		return fmt.Sprintf("number %d", t.Num)
	case TString:
		return fmt.Sprintf("string %q", t.Text)
	}
	return fmt.Sprintf("'%s'", t.Text)
}

func (p *Parser) peek() Token { return p.toks[p.pos] }

func (p *Parser) next() Token {
	t := p.toks[p.pos]
	if t.Kind != TEOF {
		p.pos++
	}
	return t
}

func (p *Parser) isPunct(s string) bool {
	t := p.peek()
	return t.Kind == TPunct && t.Text == s
}

func (p *Parser) isKeyword(s string) bool {
	t := p.peek()
	return t.Kind == TKeyword && t.Text == s
}

func (p *Parser) expect(s string) Token {
	t := p.peek()
	if (t.Kind == TPunct || t.Kind == TKeyword) && t.Text == s {
		return p.next()
	}
	fail(t.Line, "expected '%s', found %s", s, describe(t))
	return t
}

// Parse builds the constants and functions of a program from tokens.
func Parse(toks []Token) (consts []*Const, funcs []*Func, err error) {
	defer recoverError(&err)
	p := &Parser{toks: toks}
	for p.peek().Kind != TEOF {
		if p.isKeyword("const") {
			consts = append(consts, p.parseConst())
		} else {
			funcs = append(funcs, p.parseFunc())
		}
	}
	return consts, funcs, nil
}

func (p *Parser) parseConst() *Const {
	p.expect("const")
	nameTok := p.next()
	if nameTok.Kind != TIdent {
		fail(nameTok.Line, "expected constant name, found %s", describe(nameTok))
	}
	p.expect("=")
	val := p.next()
	if val.Kind != TNum {
		fail(val.Line, "a constant must be a number or a character")
	}
	p.expect(";")
	return &Const{Name: nameTok.Text, Val: val.Num, Line: nameTok.Line}
}

func (p *Parser) parseFunc() *Func {
	kw := p.expect("fn")
	nameTok := p.next()
	if nameTok.Kind != TIdent {
		fail(nameTok.Line, "expected function name, found %s", describe(nameTok))
	}
	f := &Func{Name: nameTok.Text, Line: kw.Line}
	p.expect("(")
	if !p.isPunct(")") {
		for {
			t := p.next()
			if t.Kind != TIdent {
				fail(t.Line, "expected parameter name, found %s", describe(t))
			}
			f.Params = append(f.Params, t.Text)
			if p.isPunct(",") {
				p.next()
				continue
			}
			break
		}
	}
	p.expect(")")
	f.Body = p.parseBlock()
	return f
}

func (p *Parser) parseBlock() []Stmt {
	p.expect("{")
	var stmts []Stmt
	for !p.isPunct("}") {
		if p.peek().Kind == TEOF {
			fail(p.peek().Line, "unexpected end of file, missing '}'")
		}
		stmts = append(stmts, p.parseStmt())
	}
	p.expect("}")
	return stmts
}

func (p *Parser) parseStmt() Stmt {
	t := p.peek()
	switch {
	case p.isKeyword("var"):
		p.next()
		nameTok := p.next()
		if nameTok.Kind != TIdent {
			fail(nameTok.Line, "expected variable name, found %s", describe(nameTok))
		}
		var initVal Expr = &NumExpr{Val: 0}
		if p.isPunct("=") {
			p.next()
			initVal = p.parseExpr()
		}
		p.expect(";")
		return &VarStmt{Name: nameTok.Text, Init: initVal, Line: nameTok.Line}

	case p.isKeyword("if"):
		p.next()
		p.expect("(")
		cond := p.parseExpr()
		p.expect(")")
		thenBody := p.parseBlock()
		var elseBody []Stmt
		if p.isKeyword("else") {
			p.next()
			if p.isKeyword("if") {
				elseBody = []Stmt{p.parseStmt()}
			} else {
				elseBody = p.parseBlock()
			}
		}
		return &IfStmt{Cond: cond, Then: thenBody, Else: elseBody}

	case p.isKeyword("while"):
		p.next()
		p.expect("(")
		cond := p.parseExpr()
		p.expect(")")
		body := p.parseBlock()
		return &WhileStmt{Cond: cond, Body: body}

	case p.isKeyword("return"):
		p.next()
		var val Expr = &NumExpr{Val: 0}
		if !p.isPunct(";") {
			val = p.parseExpr()
		}
		p.expect(";")
		return &ReturnStmt{Val: val}

	case t.Kind == TIdent && p.toks[p.pos+1].Kind == TPunct && p.toks[p.pos+1].Text == "=":
		p.next()
		p.next()
		val := p.parseExpr()
		p.expect(";")
		return &AssignStmt{Name: t.Text, Val: val, Line: t.Line}
	}

	x := p.parseExpr()
	p.expect(";")
	return &ExprStmt{X: x}
}

var binPrec = map[string]int{
	"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
	"==": 6, "!=": 6,
	"<": 7, "<=": 7, ">": 7, ">=": 7,
	"<<": 8, ">>": 8,
	"+": 9, "-": 9,
	"*": 10, "/": 10, "%": 10,
}

func (p *Parser) parseExpr() Expr { return p.parseBinary(1) }

func (p *Parser) parseBinary(minPrec int) Expr {
	left := p.parseUnary()
	for {
		t := p.peek()
		if t.Kind != TPunct {
			return left
		}
		prec, ok := binPrec[t.Text]
		if !ok || prec < minPrec {
			return left
		}
		p.next()
		right := p.parseBinary(prec + 1)
		left = &BinaryExpr{Op: t.Text, L: left, R: right}
	}
}

func (p *Parser) parseUnary() Expr {
	if p.isPunct("-") || p.isPunct("!") {
		op := p.next().Text
		return &UnaryExpr{Op: op, X: p.parseUnary()}
	}
	return p.parsePrimary()
}

func (p *Parser) parsePrimary() Expr {
	t := p.next()
	switch t.Kind {
	case TNum:
		return &NumExpr{Val: t.Num}
	case TString:
		return &StrExpr{Val: t.Text, Line: t.Line}
	case TIdent:
		if p.isPunct("(") {
			p.next()
			call := &CallExpr{Name: t.Text, Line: t.Line}
			if !p.isPunct(")") {
				for {
					call.Args = append(call.Args, p.parseExpr())
					if p.isPunct(",") {
						p.next()
						continue
					}
					break
				}
			}
			p.expect(")")
			return call
		}
		return &VarExpr{Name: t.Text, Line: t.Line}
	case TPunct:
		if t.Text == "(" {
			e := p.parseExpr()
			p.expect(")")
			return e
		}
	}
	fail(t.Line, "unexpected %s", describe(t))
	return nil
}
