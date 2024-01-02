function onOpen() {
  var ui = SpreadsheetApp.getUi();
  // カスタムメニューを作成
  ui.createMenu('株価操作')
      .addItem('銘柄シートを作成', 'createStockSheets')
      .addItem('銘柄シートを全て削除', 'deleteStockSheets')
      .addItem('アクティブシートの株価情報を削除', 'clearStockPriceData')
      .addItem('全ての銘柄シートの株価情報を削除', 'clearAllStockPriceData')
      .addToUi();
}

// POST関数
function doPost(e) {
  var jsonData = JSON.parse(e.postData.contents);

  var processResult = processStockData(jsonData);
  var updateResult = updateListSheet(jsonData);

  var response = {
    "processStockData": processResult,
    "updateListSheet": updateResult
  };

  return ContentService.createTextOutput(JSON.stringify(response)).setMimeType(ContentService.MimeType.JSON);
}


// GET関数
function doGet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('list');
  var tickers = sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getValues();
  var tickerCodes = tickers.map(function(row) {
    return row[0] + "." + row[1];
  });
  return ContentService.createTextOutput(JSON.stringify(tickerCodes)).setMimeType(ContentService.MimeType.JSON);
}


function processStockData(jsonData) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var errorMessages = [];

  for (var ticker in jsonData) {
    var sheet = ss.getSheetByName(ticker);
    if (sheet) {
      var stockData = jsonData[ticker];
      for (var i = 0; i < stockData.length; i++) {
        var date = stockData[i].date;
        var lastRow = sheet.getLastRow();
        var existingDateRange = sheet.getRange(1, 1, lastRow, 1).getValues();
        // var existingDateRange = sheet.getRange("A:A").getValues();
        var existingRowIndex = findExistingRowIndex(existingDateRange, date);
        
        if (existingRowIndex === -1) {
          var rowData = [date, stockData[i].open, stockData[i].high, stockData[i].low, stockData[i].close];
          var insertRowIndex = findInsertRowIndex(existingDateRange, date);
          sheet.insertRows(insertRowIndex);
          sheet.getRange(insertRowIndex, 1, 1, 5).setValues([rowData]);
        }
      }
    } else {
      var errorMessage = "Sheet for ticker " + ticker + " does not exist.";
      errorMessages.push(errorMessage);
      logError(errorMessage);
    }
  }

  if (errorMessages.length > 0) {
    return { "status": "error", "messages": errorMessages };
  } else {
    return { "status": "success" };
  }
}


// 銘柄群の株価情報を元に営業日終値差分を算出してlistシートを更新する
function updateListSheet(jsonData) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var listSheet = ss.getSheetByName('list');
  var tickers = Object.keys(jsonData);
  var errorMessages = [];

  // 定数
  var CLOSE_PRICE_COLUMN = colidx("E"); // 終値が格納されている列
  var LATEST_CLOSE_PRICE_COLUMN = colidx("Y"); // listシートで最新終値を記録する列
  var DIFFERENCE_START_COLUMN = colidx("Z"); // 差分を記録する開始列
  var SPARKLINE_COLUMN = colidx("AG"); // R列にスパークラインを記録する
  var DIFFERENCE_NUM = 7;

  // J,K,L,M,N列のヘッダから差分を取得
  var headerValues = listSheet.getRange(1, DIFFERENCE_START_COLUMN, 1, DIFFERENCE_NUM).getValues()[0]; // 10, 11, 12, 13, 14列
  var businessDayDifferences = headerValues.map(function(value) {
    return value.split(":").map(Number);
  });

  for (var i = 0; i < tickers.length; i++) {
    var ticker = tickers[i];
    var stockSheet = ss.getSheetByName(ticker);
    if (stockSheet) {
      var lastRow = stockSheet.getLastRow();
      if (lastRow <= 1) { // データまだ無い場合
        return;
      }
      var latestClosePrice = stockSheet.getRange(lastRow, CLOSE_PRICE_COLUMN).getValue(); // 最新日付の終値 (追加箇所)
      for (var j = 0; j < businessDayDifferences.length; j++) {
        var difference = businessDayDifferences[j];
        var startPrice = stockSheet.getRange(lastRow - difference[0], 5).getValue();
        var endPrice = stockSheet.getRange(lastRow - difference[1], 5).getValue();
        var priceDifference = startPrice - endPrice;
        var tickerRow = findTickerRow(listSheet, ticker);
        if (tickerRow > 0) {
          listSheet.getRange(tickerRow, LATEST_CLOSE_PRICE_COLUMN).setValue(latestClosePrice); // I列に最新日付の終値をセット (追加箇所)
          listSheet.getRange(tickerRow, DIFFERENCE_START_COLUMN + j).setValue(priceDifference); // 10, 11, 12, 13, 14列
        } else {
          errorMessages.push("Row not found for ticker " + ticker);
        }
      }

      // スパークラインの追加
      var last7ClosePricesRange = stockSheet.getRange(lastRow - 6, CLOSE_PRICE_COLUMN, DIFFERENCE_NUM, 1);
      var stockSheetName = stockSheet.getName();
      var sparklineFormula = "=SPARKLINE(" + stockSheetName + "!" + last7ClosePricesRange.getA1Notation() + ")"; // SPARKLINE関数を生成
      listSheet.getRange(tickerRow, SPARKLINE_COLUMN).setFormula(sparklineFormula); // Q列に設定
    } else {
      errorMessages.push("Sheet not found for ticker " + ticker);
    }
  }

  if (errorMessages.length > 0) {
    return { "status": "error", "messages": errorMessages };
  } else {
    return { "status": "success" };
  }
}

// 指定した銘柄の行を見つける補助関数
function findTickerRow(sheet, ticker) {
  var tickerCode = ticker.split(".")[0]; // 銘柄コードを取得
  var marketCode = ticker.split(".")[1]; // 市場コードを取得
  var tickers = sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getValues(); // AとB列

  for (var i = 0; i < tickers.length; i++) {
    if (String(tickers[i][0]) === tickerCode && tickers[i][1] === marketCode) {
      return i + 2; // 0-based index + header row
    }
  }

  return -1; // Not found
}

// 列番号を返す補助関数
function colidx(letter) {
  var column = 0;
  var length = letter.length;
  for (var i = 0; i < length; i++) {
    column += (letter.charCodeAt(i) - 'A'.charCodeAt(0) + 1) * Math.pow(26, length - i - 1);
  }
  return column;
}

// 日付情報をフォーマットする補助関数
function formatDate(dateObj) {
  return dateObj.getFullYear() + '-' +
         String(dateObj.getMonth() + 1).padStart(2, '0') + '-' +
         String(dateObj.getDate()).padStart(2, '0');
}

// 存在するかどうかを確認する補助関数
function findExistingRowIndex(dateRange, date) {
  for (var i = 1; i < dateRange.length; i++) {
    if (dateRange[i][0]) {
      var existingDateString = formatDate(new Date(dateRange[i][0]));
      if (existingDateString === date) {
        return i + 1;  // +1 to account for 0-based index
      }
    }
  }
  return -1;  // Date not found in range
}

// 挿入すべき行を求める補助関数
function findInsertRowIndex(dateRange, date) {
  for (var i = 1; i < dateRange.length; i++) { // Start from index 1 to skip the header row
    if (dateRange[i][0]) {
      if (dateRange[i][0] === "") {
        return i + 1;
      }
      var existingDateString = formatDate(new Date(dateRange[i][0]));
      if (date < existingDateString) {
        return i + 1; // Return the correct row index considering the header row
      }
    }
  }
  return dateRange.length + 1; // Return the correct row index for appending
}

