// 配当データの受信と list シートの配当列更新、派生指標(V/W/X)の算出。
//
// payload: { "type": "dividend", "data": { "6539.T": [配当0..10], ... } }
//   各配列は「配当0(最新確定年度) 〜 配当10(10年前)」の順。null は欠損(取得不可)。
//
// list 列対応:
//   I  = 配当(最新=配当0)
//   J,K,L,M,N,O,P,Q,R,S,T = 配当10, 配当9, ..., 配当1, 配当0
//   V  = 連増（減配していない連続年数）
//   W  = 維持（前年比同一の年数・通算）
//   X  = 減配（前年比減配の年数・通算）
//   U  = =SPARKLINE(L:T) の数式のため GAS では触らない。

function updateDividends(data) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var listSheet = ss.getSheetByName('list');
  var errorMessages = [];

  var COL_I = colidx("I"); // 配当(最新)
  var COL_J = colidx("J"); // 配当10
  var COL_T = colidx("T"); // 配当0
  var COL_V = colidx("V");
  var COL_W = colidx("W");
  var COL_X = colidx("X");

  for (var ticker in data) {
    var series = data[ticker]; // [配当0, 配当1, ..., 配当10]
    var row = findTickerRow(listSheet, ticker);
    if (row <= 0) {
      errorMessages.push("Row not found for ticker " + ticker);
      continue;
    }

    // 配当0..10 を T..J に書き込む。null/undefined(=None)はスキップして既存値を残す。
    for (var i = 0; i < series.length; i++) {
      var v = series[i];
      if (v === null || v === undefined) continue;
      listSheet.getRange(row, COL_T - i).setValue(v); // 配当0=T, 配当i=T-i
    }

    // I列(最新の年間配当=配当0)も更新する。
    if (series.length > 0 && series[0] !== null && series[0] !== undefined) {
      listSheet.getRange(row, COL_I).setValue(series[0]);
    }

    // V/W/X は更新後(マージ後)の配当列 J..T(=配当10..配当0=古→新) から計算する。
    var merged = listSheet.getRange(row, COL_J, 1, COL_T - COL_J + 1).getValues()[0];
    var metrics = computeDividendMetrics(merged);
    listSheet.getRange(row, COL_V).setValue(metrics.V);
    listSheet.getRange(row, COL_W).setValue(metrics.W);
    listSheet.getRange(row, COL_X).setValue(metrics.X);
  }

  if (errorMessages.length > 0) {
    return { "status": "error", "messages": errorMessages };
  }
  return { "status": "success" };
}

// 配当列(古→新)から V(連増)/W(維持)/X(減配) を算出する。
// values: J..T = 配当10..配当0(古い順)。空文字/null は欠損として除外する。
// ロジックは Python の dividend_updater.dividend_metrics と一致させること。
function computeDividendMetrics(values) {
  var vals = [];
  for (var i = 0; i < values.length; i++) {
    var v = values[i];
    if (v === "" || v === null || v === undefined) continue;
    vals.push(Number(v));
  }

  var transitions = []; // 'up' / 'flat' / 'down'（古→新）
  for (var i = 1; i < vals.length; i++) {
    if (vals[i] > vals[i - 1]) transitions.push('up');
    else if (vals[i] === vals[i - 1]) transitions.push('flat');
    else transitions.push('down');
  }

  var w = 0, x = 0;
  for (var i = 0; i < transitions.length; i++) {
    if (transitions[i] === 'flat') w++;
    else if (transitions[i] === 'down') x++;
  }

  // V: 最新(末尾)から遡って down でない限り連続加算
  var v = 0;
  for (var i = transitions.length - 1; i >= 0; i--) {
    if (transitions[i] === 'down') break;
    v++;
  }

  return { V: v, W: w, X: x };
}
