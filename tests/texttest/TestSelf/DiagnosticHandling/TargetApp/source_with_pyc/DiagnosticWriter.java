
// javac -classpath /usr/share/java/log4j.jar DiagnosticWriter.java
  
import org.apache.log4j.*;
import java.io.*;
import java.util.*;

class DiagnosticWriter
{
  public static boolean setupConfigFile()
  {
    Properties props = new Properties();
    try 
    {
      FileInputStream input = new FileInputStream("myprops.properties");
      props.load(input);
      String log4jconfigfile = props.getProperty("TESTDIAG_READFILE");
      File config = new File(log4jconfigfile);
      if (config.exists())
        PropertyConfigurator.configure(log4jconfigfile);
      else
        System.out.println("Failed to find property file");
      return true;
    }
    catch (FileNotFoundException exc)
    {
      System.out.println("Failed to find property file");
    }
    catch (IOException exc)
    {
      System.out.println("Failed to read property file");
    }
    return false;
  }

  public static void main(String [] args)
  {
    System.out.println("This is a simple diagnostic-writing program");
    if (!setupConfigFile())
      return;

    Logger logger1 = Logger.getLogger("firstdiag");
    logger1.info("Some information");
    logger1.debug("Some debug stuff");

    Logger logger2 = Logger.getLogger("seconddiag");
    logger2.info("Some information");
    logger2.debug("Some debug stuff");

    Logger logger3 = Logger.getLogger("thirddiag");
    logger3.info("Some information");
    logger3.debug("Some debug stuff");
  }
}
