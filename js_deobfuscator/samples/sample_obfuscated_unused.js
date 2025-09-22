var a = 1;
var b = 2;
function used_func() {
    return a;
}
function unused_func() {
    return 42;
}
console.log(used_func());
