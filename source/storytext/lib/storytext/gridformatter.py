
""" Module for laying out text in a grid pattern. Should not depend on anything but string manipulation """

class GridFormatter:
    def __init__(self, grid, numColumns, maxWidth=None, columnSpacing=2, allowOverlap=True):
        self.grid = grid
        self.numColumns = numColumns
        self.maxWidth = maxWidth
        self.columnSpacing = columnSpacing
        self.allowOverlap = allowOverlap

    def __str__(self):
        colWidths = self.findColumnWidths()
        totalWidth = sum(colWidths)
        if self.maxWidth is not None and totalWidth > self.maxWidth: # After a while, excessively wide grids just get too hard to read
            header = "." * 6 + " " + str(self.numColumns) + "-Column Layout " + "." * 6
            desc = self.formatColumnsInGrid()
            footer = "." * len(header)
            return header + "\n" + desc + "\n" + footer
        else:
            return self.formatCellsInGrid(colWidths)

    def isHorizontalRow(self):
        return len(self.grid) == 1 and self.numColumns > 1

    def findColumnWidths(self):
        colWidths = [ 0 ] * self.numColumns
        for colNum in reversed(range(self.numColumns)):
            cellWidths = set((self.getCellWidth(rowIx, row, colNum, colWidths) for rowIx, row in enumerate(self.grid)))
            maxWidth = max(cellWidths) or -min(cellWidths)
            colWidths[colNum] = maxWidth
        return colWidths

    def getCellWidth(self, rowIx, row, colNum, colWidths):
        if colNum < len(row):
            cellText = row[colNum]
            lines = cellText.splitlines()
            if lines:
                realMaxWidth = max((len(line) for line in lines))
                if colNum != len(row) - 1 and realMaxWidth > 0:
                    realMaxWidth += self.columnSpacing
                if not self.allowOverlap or not self.allowOverlapInCell(rowIx, colNum, cellText):
                    return realMaxWidth
                
                c = colNum + 1
                maxWidth = realMaxWidth
                # If the following columns are empty, assume we can overlap them
                while maxWidth > 0 and c < self.numColumns and (c >= len(row) or len(row[c]) == 0):
                    maxWidth -= colWidths[c]
                    c += 1
                maxWidth = max(maxWidth, 0)
                if realMaxWidth and not maxWidth:
                    return -realMaxWidth # our way of saying 'use this if there is nothing else in this column'
                else:
                    return maxWidth
        return 0

    def allowOverlapInCell(self, row, colNum, cellText):
        # Hook for derived classes to allow overlapping in some grid regions and not others
        return True

    def formatColumnsInGrid(self):
        desc = ""
        for colNum in range(self.numColumns):
            for row in self.grid:
                if colNum < len(row):
                    desc += row[colNum] + "\n"
            desc += "\n"
        return desc.rstrip()

    def formatCellsInGrid(self, colWidths):
        lines = []
        for row in self.grid:
            rowLines = max((desc.count("\n") + 1 for desc in row))
            for rowLine in range(rowLines):
                lineText = ""
                currPos = 0
                for colNum, childDesc in enumerate(row):
                    cellLines = childDesc.splitlines()
                    if rowLine < len(cellLines):
                        cellRow = cellLines[rowLine]
                    else:
                        cellRow = ""
                    if cellRow and len(lineText) > currPos:
                        lineText = lineText[:currPos]
                    lineText += cellRow.ljust(colWidths[colNum])
                    currPos += colWidths[colNum]
                lines.append(lineText.rstrip(" ")) # don't leave trailing spaces        
        return "\n".join(lines)
