describe("the tests for propertyCount", function () {

  it("counts the object's own members", function () {
    var ob = {
      a: 0,
      b: "two",
      c: [1, 2, 3]
    };
    expect(propertyCount(ob)).toBe(3);
  });

  it("doesn't count the superclass's members", function () {
    function f () {};
    f.prototype.a = "super property";
    var ob = new f();
    expect(ob.a).toBe("super property");
    expect(propertyCount(ob)).toBe(0);
  });
});
