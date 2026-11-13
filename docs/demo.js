"use strict";

const people = [
  { id: "DEMO01", name: "Alex Chen" },
  { id: "DEMO02", name: "Mina Rahman" },
  { id: "DEMO03", name: "Sam Lee" },
];
const byId = id => document.getElementById(id);
const face = byId("face");
const personFilter = byId("person-filter");
const dateFilter = byId("date-filter");
const result = byId("scan-result");

function localDate(value = new Date()) {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

function demoRecords() {
  return [[0, 2], [1, 2], [0, 1]].flatMap((ids, index) => {
    const day = new Date();
    day.setDate(day.getDate() - index - 1);
    return ids.map((person, slot) => ({
      ...people[person], date: localDate(day), time: slot ? "09:08:00" : "09:04:00",
    }));
  });
}

let records = demoRecords();
for (const person of people) {
  face.add(new Option(person.name, person.id));
  personFilter.add(new Option(person.name, person.id));
}
face.value = people[0].id;
byId("people-count").textContent = people.length;

function filteredRecords() {
  return records.filter(record =>
    (!dateFilter.value || record.date === dateFilter.value) &&
    (!personFilter.value || record.id === personFilter.value)
  ).sort((a, b) => `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`));
}

function render() {
  byId("present-count").textContent = records.filter(record => record.date === localDate()).length;
  const visible = filteredRecords();
  byId("record-count").textContent = visible.length
    ? `${visible.length} records shown`
    : "No attendance matches these filters.";
  const rows = visible.map(record => {
    const row = document.createElement("tr");
    for (const value of [record.id, record.name, record.date, record.time, "Present"]) {
      row.insertCell().textContent = value;
    }
    return row;
  });
  byId("records").replaceChildren(...rows);
}

byId("scan-form").addEventListener("submit", event => {
  event.preventDefault();
  const person = people.find(entry => entry.id === face.value);
  if (!person) {
    result.textContent = "Unknown visitor. No attendance recorded.";
    return;
  }
  const now = new Date();
  const date = localDate(now);
  if (records.some(record => record.id === person.id && record.date === date)) {
    result.textContent = `${person.name} is already marked today.`;
    return;
  }
  records.push({ ...person, date, time: now.toTimeString().slice(0, 8) });
  result.textContent = `${person.name} marked present.`;
  render();
});
dateFilter.addEventListener("change", render);
personFilter.addEventListener("change", render);
byId("reset").addEventListener("click", () => {
  records = demoRecords();
  dateFilter.value = "";
  personFilter.value = "";
  face.value = people[0].id;
  result.textContent = "Demo reset. Ready for a simulated scan.";
  render();
});
byId("export").addEventListener("click", () => {
  const lines = filteredRecords().map(record =>
    [record.id, record.name, record.date, record.time, "Present"].join(",")
  );
  const csv = ["student_id,name,date,time,status", ...lines].join("\r\n") + "\r\n";
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "attendance-demo.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
render();
