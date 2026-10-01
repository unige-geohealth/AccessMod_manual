-- PDF (Typst) only: give table columns widths proportional to their content
-- (the HTML coming from Confluence carried no usable column widths).
local function cell_len(cell)
  return utf8.len(pandoc.utils.stringify(cell.contents)) or 0
end

function Table(tbl)
  local n = #tbl.colspecs
  local maxlen = {}
  for i = 1, n do maxlen[i] = 3 end
  local function scan(rows)
    for _, row in ipairs(rows) do
      local col = 1
      for _, cell in ipairs(row.cells) do
        if col <= n and (cell.col_span or 1) == 1 then
          maxlen[col] = math.max(maxlen[col], math.min(cell_len(cell), 80))
        end
        col = col + (cell.col_span or 1)
      end
    end
  end
  scan(tbl.head.rows)
  for _, body in ipairs(tbl.bodies) do scan(body.body) end
  local total = 0
  for i = 1, n do maxlen[i] = math.max(maxlen[i], 8); total = total + maxlen[i] end
  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = { spec[1], maxlen[i] / total }
  end
  return tbl
end
