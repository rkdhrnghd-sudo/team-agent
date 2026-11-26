// 기여도 판 그리기. 팀장 화면(lead.html)과 팀원 화면(me.html)이 같이 쓴다.
function renderBoard(box, data) {
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const pct = x => `${Math.round(x * 100)}%`;
  box.replaceChildren();

  const table = el("table", "board");
  const head = el("tr");
  ["이름", "통과 / 맡은 시간", "진행률", "기여도", "기한 지킴", "늦게 냄", "보완 횟수", "마감 지난 미제출", "응답 없음"].forEach(t => head.append(el("th", "", t)));
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  data.contribution.forEach(r => {
    const tr = el("tr");
    tr.append(el("td", "", r.name));
    tr.append(el("td", "", `${r.passed} / ${r.planned}시간`));
    const prog = el("td");
    const bar = el("div", "bar");
    const fill = el("div", "fill");
    fill.style.width = pct(r.progress);
    bar.append(fill);
    prog.append(bar, el("span", "bar-label", pct(r.progress)));
    tr.append(prog);
    tr.append(el("td", "", pct(r.share)));
    tr.append(el("td", "", `${r.on_time}개`));
    tr.append(el("td", r.late ? "warn" : "", `${r.late}개`));
    tr.append(el("td", r.fix_count ? "warn" : "", `${r.fix_count}번`));
    tr.append(el("td", r.overdue ? "warn" : "", `${r.overdue}개`));
    tr.append(el("td", r.no_reply ? "warn" : "", `${r.no_reply || 0}개`));
    tbody.append(tr);
  });
  const sum = el("tr", "sum");
  sum.append(el("td", "", "팀 전체"));
  sum.append(el("td", "", `${data.team_passed} / ${data.team_planned}시간`));
  sum.append(el("td", "", data.team_planned ? pct(data.team_passed / data.team_planned) : "0%"));
  sum.append(el("td", "", data.team_passed ? "100%" : "0%"));
  ["", "", "", "", ""].forEach(t => sum.append(el("td", "", t)));
  tbody.append(sum);
  table.append(thead, tbody);
  box.append(table);
  box.append(el("p", "board-note",
    `기여도 = 그 사람이 통과한 예상 시간 ÷ 팀 전체가 통과한 예상 시간. 진행률 = 통과한 시간 ÷ 맡은 시간. ` +
    `응답 없음 = 같은 할 일 알림이 3번을 넘었는데 안 낸 할 일 수. 기준일 ${data.today}.`));
}
