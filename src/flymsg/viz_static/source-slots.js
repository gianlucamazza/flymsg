// Stable fragment submission order, including re-used holes. Match the pinned
// reference renderer's public instance allocation without allocating its arena.
export class SourceSlots {
  constructor(limit) {
    this.limit = limit;
    this.reset();
  }
  reset() {
    this.next = 0;
    this.free = [];
    this.active = new Set();
  }
  allocate() {
    if (!this.free.length && this.next >= this.limit)
      throw new RangeError("Source instance capacity exhausted");
    const id = this.free.length
      ? this.free.sort((a, b) => b - a).pop()
      : this.next++;
    this.active.add(id);
    return id;
  }
  release(id) {
    if (!this.active.delete(id))
      throw new Error("Source instance already released");
    this.free.push(id);
  }
}
