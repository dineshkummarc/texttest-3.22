
from storytext.javaswttoolkit import describer as swtdescriber
from storytext import guishared, gridformatter
import org.eclipse.draw2d as draw2d
from org.eclipse import swt

class ColorNameFinder:
    abbrevations = [ ("dark", "+"), ("dull", "#"), ("very", "+"),
                     ("light", "-"), ("normal", ""), ("bright", "*") ]
    def __init__(self):
        self.names = {}
        self.addColors(draw2d.ColorConstants)
    
    def shortenColorName(self, name):
        ret = name.lower()
        for text, repl in self.abbrevations:
            ret = ret.replace(text, repl)
        return ret

    def addColors(self, cls):
        for name in sorted(cls.__dict__):
            if not name.startswith("__"):
                color = getattr(cls, name)
                if hasattr(color, "getRed"):
                    self.names[self.getRGB(color)] = self.shortenColorName(name)

    def getRGB(self, color):
        return color.getRed(), color.getGreen(), color.getBlue()

    def getName(self, color):
        return self.names.get(self.getRGB(color), "unknown")
        
colorNameFinder = ColorNameFinder()


class Describer(swtdescriber.Describer):
    def describeStructure(self, widget, indent=0, **kw):
        swtdescriber.Describer.describeStructure(self, widget, indent, **kw)
        if self.hasFigureCanvasAPI(widget):
            self.describeStructure(widget.getContents(), indent+1,
                                   visibleMethodNameOverride="isVisible", layoutMethodNameOverride="getLayoutManager")

    def hasFigureCanvasAPI(self, widget):
        # Could just check for FigureCanvas, but sometimes basic Canvases are used with the Figure mechanisms there also
        # (usually when scrolling not desired to disable mouse-wheel usage)
        return isinstance(widget, swt.widgets.Canvas) and hasattr(widget, "getContents")

    def getCanvasDescription(self, widget):
        if hasattr(widget, "getContents"): # FigureCanvas and others sharing its API
            return self.getAndStoreState(widget)
        else:
            return swtdescriber.Describer.getCanvasDescription(self, widget)

    def getCanvasState(self, widget):
        return FigureCanvasDescriber().getDescription(widget.getContents())
            
    def getUpdatePrefix(self, widget, *args):
        if self.hasFigureCanvasAPI(widget):
            return "\nUpdated Canvas :\n"
        else:
            return swtdescriber.Describer.getUpdatePrefix(self, widget, *args)

class AttrRecorder:
    def __init__(self, name, recorder):
        self.name = name
        self.recorder = recorder
        
    def __call__(self, *args):
        self.recorder.registerCall(self.name, args)

        
class RecorderGraphics(draw2d.Graphics, object):
    def __init__(self, font, methodNames):
        self.calls = []
        self.currFont = font
        self.methodNames = methodNames
        
    def __getattribute__(self, name):
        if name in object.__getattribute__(self, "methodNames"):
            return AttrRecorder(name, self)
        else:
            return object.__getattribute__(self, name)

    def drawRectangle(self, *args):
        pass # Overloaded, causes loop above. Don't want to draw this stuff anyway...

    def fillRectangle(self, *args):
        pass # Overloaded, causes loop above. Don't want to draw this stuff anyway...

    def setLineAttributes(self, *args):
        pass # throws NotImplemented by default

    def getFont(self):
        return self.currFont

    def setFont(self, font):
        self.currFont = font

    def registerCall(self, methodName, args):
        self.calls.append((methodName, args))

    def getCallArgs(self, methodName):
        return [ c[1] for c in self.calls if c[0] == methodName ]

    def getCallGroups(self, methodNames):
        result = []
        prevIx = len(methodNames)
        for methodName, args in self.calls:
            if methodName in methodNames:
                ix = methodNames.index(methodName)
                if ix <= prevIx:
                    result.append([ None ] * len(methodNames))
                result[-1][ix] = args
                prevIx = ix
        return result


class FigureCanvasDescriber(guishared.Describer):
    childrenMethodName = "getChildren"
    visibleMethodName = "isVisible"
    statelessWidgets = [ draw2d.RectangleFigure, draw2d.Label, draw2d.PolylineShape ]
    stateWidgets = []
    ignoreWidgets = [ draw2d.Figure ] # Not interested in anything except what we list
    ignoreChildren = ()
    pixelTolerance = 2
    def getLabelDescription(self, figure):
        return figure.getText()
    
    def getRectangleFigureDescription(self, figure):
        font = figure.getFont()
        graphics = RecorderGraphics(font, [ "drawString", "setBackgroundColor", "fillRectangle" ])
        figure.paintFigure(graphics)
        calls = graphics.getCallArgs("drawString")
        callGroups = graphics.getCallGroups([ "setBackgroundColor", "fillRectangle" ])
        color = figure.getBackgroundColor()
        filledRectangles = []
        bounds = figure.getBounds()
        fontSize = font.getFontData()[0].getHeight()
        for colorArgs, rectArgs in callGroups:
            rect = draw2d.geometry.Rectangle(*rectArgs)
            filledRectangles.append(rect)
            colorText = ""
            if colorArgs is not None:
                rectColor = colorArgs[0]
                if rectColor != color:
                    colorText = "(" + colorNameFinder.getName(rectColor) + ")"
                if rect != bounds and colorText:
                    self.addColouredRectangle(calls, colorText, rect, fontSize)
        calls.sort(key=lambda (t, x, y): (y, x))
        colorText = colorNameFinder.getName(color) if self.changedColor(color, figure) else ""
        return self.formatFigure(figure, calls, colorText, filledRectangles)

    def addColouredRectangle(self, calls, colorText, rect, fontSize):
        # Find some text to apply it to, if we can
        for i, (text, x, y) in enumerate(calls):
            # Adding pixels to "user space units". Is this always allowed?
            if rect.contains(x, y) or rect.contains(x, y + fontSize):
                calls[i] = text + colorText, x, y
                return
        calls.append((colorText, self.getInt(rect.x), self.getInt(rect.y)))

    def changedColor(self, color, figure):
        return color != figure.getParent().getBackgroundColor()

    def formatFigure(self, figure, calls, colorText, filledRectangles):
        desc = self.arrangeText(calls)
        if isinstance(desc, gridformatter.GridFormatter):
            return desc
        if colorText:
            desc += "(" + colorText + ")"
        return self.addBorder(figure, desc)

    def addBorder(self, figure, desc):
        if figure.getBorder():
            return "[ " + desc + " ]"
        else:
            return desc

    def arrangeText(self, calls):
        if len(calls) == 0:
            return ""
        elif len(calls) == 1:
            return calls[0][0]
        else:
            grid, numColumns = self.makeTextGrid(calls)
            return self.formatGrid(grid, numColumns)

    def formatGrid(self, grid, numColumns):
        return gridformatter.GridFormatter(grid, numColumns)

    def usesGrid(self, figure):
        return isinstance(figure, draw2d.RectangleFigure)

    def makeTextGrid(self, calls):
        grid = []
        prevY = None
        xColumns = []
        for text, x, y in calls:
            if prevY is None or abs(y - prevY) > self.pixelTolerance: # some pixel forgiveness...
                grid.append([])
            index = self.findExistingColumn(x, xColumns)
            if index is None:
                if len(grid) == 1:
                    index = len(xColumns)
                    xColumns.append(x)
                else:
                    index = self.findIndex(x, xColumns)
                    xColumns.insert(index, x)
                    for row in range(len(grid) - 1):
                        if index < len(grid[row]):
                            grid[row].insert(index, "")
            while len(grid[-1]) < index:
                grid[-1].append("")
            grid[-1].append(text)
            prevY = y

        if len(grid) > 0:
            return grid, max((len(r) for r in grid))
        else:
            return None, 0

    def findExistingColumn(self, x, xColumns): # more pixel forgiveness
        for attempt in xrange(x - self.pixelTolerance, x + self.pixelTolerance + 1):
            if attempt in xColumns:
                return xColumns.index(attempt)    

    def findIndex(self, x, xColumns):
        # linear search, replace with bisect?
        for ix, currX in enumerate(xColumns):
            if x < currX:
                return ix
        return len(xColumns)

    def tryMakeGrid(self, figure, sortedChildren, childDescriptions):
        if all((isinstance(c, gridformatter.GridFormatter) for c in childDescriptions)):
            newGrid = []
            for i, childDesc in enumerate(childDescriptions):
                newGrid += childDesc.grid
                if i != len(childDescriptions) - 1:
                    newGrid.append([ "" ])
            return newGrid, max((c.numColumns for c in childDescriptions))
        else:
            calls = [ self.makeCall(desc, child) for desc, child in zip(childDescriptions, sortedChildren) ]
            return self.makeTextGrid(calls)

    def makeCall(self, desc, child):
        loc = child.getLocation()            
        # x and y should be public fields, and are sometimes. In our tests, they are methods, for some unknown reason
        return str(desc), self.getInt(loc.x), self.getInt(loc.y)

    def getInt(self, intOrMethod):
        return intOrMethod if isinstance(intOrMethod, int) else intOrMethod()
            
    def layoutSortsChildren(self, widget):
        return False
    
    def getVerticalDividePositions(self, visibleChildren):
        return []

    def handleGridFormatter(self, formatter):
        return formatter # It's not a horizontal row, but we want to be able to combine grids with each other
