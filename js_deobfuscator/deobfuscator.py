import esprima
import jsbeautifier
import escodegen
from asteval import Interpreter
import re
from collections import Counter

class AstVisitor:
    def visit(self, node):
        if node is None: return
        if isinstance(node, list):
            for item in node: self.visit(item)
            return
        if not hasattr(node, 'type') or node.type is None: return
        for field in dir(node):
            if not (field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']):
                value = getattr(node, field)
                if hasattr(value, 'type'): setattr(value, 'parent', node)
                elif isinstance(value, list):
                    for child in value:
                        if hasattr(child, 'type'): setattr(child, 'parent', node)
        method_name = 'visit_' + node.type
        visitor = getattr(self, method_name, self.generic_visit)
        visitor(node)
    def generic_visit(self, node):
        for field in dir(node):
            if field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']: continue
            value = getattr(node, field)
            if value is None: continue
            self.visit(value)

class AstTransformer(AstVisitor):
    def visit(self, node):
        if node is None: return None
        if isinstance(node, list):
            new_list = []
            for item in node:
                new_item = self.visit(item)
                if new_item is not None:
                    if isinstance(new_item, list): new_list.extend(new_item)
                    else: new_list.append(new_item)
            return new_list
        if not hasattr(node, 'type') or node.type is None: return node
        for field in dir(node):
            if not (field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']):
                value = getattr(node, field)
                if hasattr(value, 'type'): setattr(value, 'parent', node)
                elif isinstance(value, list):
                    for child in value:
                        if hasattr(child, 'type'): setattr(child, 'parent', node)
        method_name = 'visit_' + node.type
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)
    def generic_visit(self, node):
        for field in dir(node):
            if field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']: continue
            old_value = getattr(node, field)
            if old_value is None: continue
            new_value = self.visit(old_value)
            setattr(node, field, new_value)
        return node

class StringArrayFinder(AstVisitor):
    def __init__(self):
        self.string_array, self.string_array_name, self.accessor_name = None, None, None
    def visit_VariableDeclarator(self, node):
        if not self.string_array and node.init and node.init.type == 'ArrayExpression':
            elements = [el.value for el in node.init.elements if el.type == 'Literal']
            if len(elements) > 2 and len(elements) == len(node.init.elements):
                self.string_array, self.string_array_name = elements, node.id.name
        elif self.string_array_name and not self.accessor_name and node.init and node.init.type == 'FunctionExpression':
             if self.string_array_name in escodegen.generate(node.init.body): self.accessor_name = node.id.name
        self.generic_visit(node)
    def visit_FunctionDeclaration(self, node):
        if self.string_array_name and not self.accessor_name:
            if self.string_array_name in escodegen.generate(node.body):
                self.accessor_name = node.id.name
        self.generic_visit(node)

class StringArrayResolver(AstTransformer):
    def __init__(self, context):
        self.context = context
        self.index_usage = Counter()
    def visit_CallExpression(self, node):
        if self.context.accessor_name and node.callee.type == 'Identifier' and node.callee.name == self.context.accessor_name:
            if len(node.arguments) == 1 and node.arguments[0].type == 'Literal':
                index = node.arguments[0].value
                if isinstance(index, int) and 0 <= index < len(self.context.string_array):
                    self.index_usage[index] += 1
                    return esprima.nodes.Literal(value=self.context.string_array[index], raw=repr(self.context.string_array[index]))
        return self.generic_visit(node)
    def visit_MemberExpression(self, node):
        if node.object.type == 'Identifier' and node.object.name == self.context.string_array_name:
            if node.property.type == 'Literal' and isinstance(node.property.value, int):
                index = node.property.value
                if 0 <= index < len(self.context.string_array):
                    self.index_usage[index] += 1
                    return esprima.nodes.Literal(value=self.context.string_array[index], raw=repr(self.context.string_array[index]))
        return self.generic_visit(node)

class VariableRenamer(AstTransformer):
    def __init__(self):
        self.scope_stack, self.var_counter, self.renamed_count = [{}], 0, 0
        self.hex_pattern = re.compile(r'^_0x[a-fA-F0-9]+$')
        self.confusing_chars_pattern = re.compile(r'^[Il1O0]+$')
    def enter_scope(self): self.scope_stack.append({})
    def leave_scope(self): self.scope_stack.pop()
    def declare_var(self, name):
        is_hex = self.hex_pattern.match(name)
        is_short = len(name) <= 2 and name not in ['i', 'j', 'k', 't', 'a', 'b', 'c', 'x', 'y', 'z']
        is_confusing = len(name) > 2 and self.confusing_chars_pattern.match(name)
        if is_hex or is_short or is_confusing:
            new_name = f"var_{self.var_counter}"; self.var_counter += 1
            self.scope_stack[-1][name] = new_name; self.renamed_count += 1
            return new_name
        self.scope_stack[-1][name] = name
        return name
    def get_new_name(self, name):
        for scope in reversed(self.scope_stack):
            if name in scope: return scope[name]
        return name
    def visit_FunctionDeclaration(self, node):
        if node.id: node.id.name = self.declare_var(node.id.name)
        self.enter_scope()
        if node.params:
            for i, param in enumerate(node.params):
                if param.type == 'Identifier': node.params[i].name = self.declare_var(param.name)
        node.body = self.visit(node.body)
        self.leave_scope()
        return node
    def visit_FunctionExpression(self, node):
        self.enter_scope()
        if node.params:
            for i, param in enumerate(node.params):
                if param.type == 'Identifier': node.params[i].name = self.declare_var(param.name)
        node.body = self.visit(node.body)
        self.leave_scope()
        return node
    def visit_VariableDeclarator(self, node):
        if node.id.type == 'Identifier': node.id.name = self.declare_var(node.id.name)
        if node.init: node.init = self.visit(node.init)
        return node
    def visit_Identifier(self, node):
        parent = getattr(node, 'parent', None)
        if parent and parent.type == 'MemberExpression' and parent.property == node and not parent.computed: return node
        node.name = self.get_new_name(node.name)
        return node

class UsageCounter(AstVisitor):
    def __init__(self): self.counts = Counter()
    def visit_Identifier(self, node):
        parent = getattr(node, 'parent', None)
        is_declaration = (parent and ((parent.type == 'VariableDeclarator' and parent.id == node) or (parent.type in ['FunctionDeclaration', 'FunctionExpression'] and parent.id == node) or (hasattr(parent, 'params') and parent.params is not None and node in parent.params)))
        is_property = parent and parent.type == 'MemberExpression' and parent.property == node and not parent.computed
        if not is_declaration and not is_property: self.counts[node.name] += 1

class ExpressionSimplifier(AstTransformer):
    def __init__(self):
        self.simplified_count = 0; self.aeval = Interpreter()
        self.valid_identifier_regex = re.compile(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$')

    def _create_literal_node(self, value):
        """Helper to create a literal node, handling negative numbers correctly."""
        if isinstance(value, (int, float)) and value < 0:
            return esprima.nodes.UnaryExpression(operator='-', argument=esprima.nodes.Literal(value=abs(value), raw=str(abs(value))))
        return esprima.nodes.Literal(value=value, raw=repr(value))

    def visit_MemberExpression(self, node):
        node = self.generic_visit(node)
        if node.computed and node.property.type == 'Literal' and isinstance(node.property.value, str):
            prop_name = node.property.value
            if self.valid_identifier_regex.match(prop_name):
                node.computed = False; node.property = esprima.nodes.Identifier(name=prop_name)
                self.simplified_count += 1
        return node
    def visit_BinaryExpression(self, node):
        node = self.generic_visit(node)
        if node.left.type == 'Literal' and node.right.type == 'Literal':
            op_map = {'&&': 'and', '||': 'or', '!==': '!=', '===': '=='}; py_op = op_map.get(node.operator, node.operator)
            try:
                result = self.aeval.eval(f"{repr(node.left.value)} {py_op} {repr(node.right.value)}")
                self.simplified_count += 1
                return self._create_literal_node(result)
            except: return node
        return node
    def visit_UnaryExpression(self, node):
        node = self.generic_visit(node)
        if node.argument.type == 'Literal':
            if node.operator == 'typeof':
                type_map = {'str': 'string', 'int': 'number', 'float': 'number', 'bool': 'boolean', 'NoneType': 'object'}; result = type_map.get(type(node.argument.value).__name__, 'object')
                self.simplified_count += 1; return self._create_literal_node(result)
            op_map = {'!': 'not '}; py_op = op_map.get(node.operator, node.operator)
            try:
                result = self.aeval.eval(f"{py_op}{repr(node.argument.value)}")
                self.simplified_count += 1
                return self._create_literal_node(result)
            except: return node
        return node

class DeadCodeEliminator(AstTransformer):
    def __init__(self, usage_counts=None):
        self.usage_counts = usage_counts if usage_counts else Counter()
        self.reserved_names = {'console', 'window', 'document', 'Array', 'Object', 'String', 'Number', 'Boolean', 'Function'}
        self.if_branches_removed, self.symbols_removed = 0, 0
    def visit_IfStatement(self, node):
        node.test = self.visit(node.test)
        if node.test.type == 'Literal':
            self.if_branches_removed += 1
            if node.test.value:
                if node.consequent and node.consequent.type == 'BlockStatement': return self.visit(node.consequent.body)
                return self.visit(node.consequent)
            else:
                if node.alternate:
                    if node.alternate.type == 'BlockStatement': return self.visit(node.alternate.body)
                    return self.visit(node.alternate)
                return None
        return self.generic_visit(node)
    def visit_FunctionDeclaration(self, node):
        if node.id and node.id.name not in self.reserved_names and self.usage_counts[node.id.name] == 0:
            self.symbols_removed += 1; return None
        return self.generic_visit(node)
    def visit_VariableDeclaration(self, node):
        declarations_to_keep = []
        for decl in node.declarations:
            is_safe_to_remove = (decl.init is None) or (decl.init.type != 'CallExpression')
            if decl.id.name not in self.reserved_names and self.usage_counts[decl.id.name] == 0 and is_safe_to_remove:
                self.symbols_removed += 1; continue
            declarations_to_keep.append(decl)
        if not declarations_to_keep: return None
        node.declarations = declarations_to_keep
        return node

def deobfuscate(js_code):
    try: ast = esprima.parse(js_code, {'comment': True})
    except Exception as e: print(f"Error parsing JavaScript: {e}"); return js_code

    string_finder = StringArrayFinder()
    string_finder.visit(ast)

    resolver = StringArrayResolver(string_finder)
    ast = resolver.visit(ast)

    renamer = VariableRenamer()
    ast = renamer.visit(ast)

    simplifier = ExpressionSimplifier()
    ast = simplifier.visit(ast)

    while True:
        usage_counter = UsageCounter()
        usage_counter.visit(ast)
        ast_before_elimination = escodegen.generate(ast)
        eliminator = DeadCodeEliminator(usage_counter.counts)
        ast = eliminator.visit(ast)
        ast_after_elimination = escodegen.generate(ast)
        if ast_before_elimination == ast_after_elimination: break

    report_data = {
        'renamed_count': renamer.renamed_count,
        'simplified_count': simplifier.simplified_count,
        'if_branches_removed': eliminator.if_branches_removed,
        'symbols_removed': eliminator.symbols_removed,
        'variable_usage': usage_counter.counts,
        'string_array_usage': resolver.index_usage
    }

    report = "/*\n--- Deobfuscation Report ---\n\n"
    report += "Statistics:\n"
    report += f"- Variables Renamed: {report_data.get('renamed_count', 0)}\n"
    report += f"- Expressions Simplified: {report_data.get('simplified_count', 0)}\n"
    report += f"- Dead If Branches Removed: {report_data.get('if_branches_removed', 0)}\n"
    report += f"- Unused Symbols Removed: {report_data.get('symbols_removed', 0)}\n\n"
    if 'variable_usage' in report_data and report_data['variable_usage']:
        report += "Variable Usage Counts:\n"
        for name, count in sorted(report_data['variable_usage'].items()):
            report += f"  - {name}: {count}\n"
    if 'string_array_usage' in report_data and report_data['string_array_usage']:
        report += "\nString Array Index Usage (top 5):\n"
        for index, count in sorted(report_data['string_array_usage'].items(), key=lambda item: item[1], reverse=True)[:5]:
            report += f"  - Index {index}: {count} times\n"
    report += "*/\n\n"

    generated_code = escodegen.generate(ast)
    return report + jsbeautifier.beautify(generated_code)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='A Python script to deobfuscate JavaScript code.')
    parser.add_argument('input_file', type=str, help='The path to the obfuscated JavaScript file.')
    parser.add_argument('output_file', type=str, help='The path to write the deobfuscated code to.')
    args = parser.parse_args()
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f: obfuscated_code = f.read()
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_file}"); return
    deobfuscated_code = deobfuscate(obfuscated_code)
    with open(args.output_file, 'w', encoding='utf-8') as f: f.write(deobfuscated_code)
    print(f"Deobfuscated code written to {args.output_file}")

if __name__ == '__main__':
    main()
