# TAMU-GradeDistribution-ParserV2: gd_main.py
# @authors: github/adibarra


# imports
from typing import List, Tuple

import os
import sys
import bs4
import requests
from alive_progress import alive_bar
from gd_utils import Utils
from gd_logger import Logger, Importance
from gd_database import DatabaseHandler
from gd_pdfparser import PDFParser


OVERWRITE_ALL_PDF = False
LEGACY_YEAR_DATA = ['2015','2014']
PDF_ROOT_LINK = 'https://web-as.tamu.edu/GradeReports/'
PDF_BASE_LINK = 'https://web-as.tamu.edu/GradeReports/PDFReports/{0}/grd{0}{1}.pdf'
PDF_SAVE_DIR  = 'pdfs/'


# scrape years and colleges from grade reports site using bs4
def scrape_report_metadata() -> Tuple[List[str],List[str]]:
    response = requests.get(PDF_ROOT_LINK)
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    years, colleges = [], []
    for option in soup.select("#ctl00_plcMain_lstGradYear > option"):
        years.append(option['value'])
    for option in soup.select("#ctl00_plcMain_lstGradCollege > option"):
        colleges.append(option['value'])
    return years, colleges


# load pdf or download from given url if not present
def load_pdf(download_url: str, no_dl=False) -> str:
    file_name = download_url.split('/')[-1]
    file_path = PDF_SAVE_DIR+file_name

    def download_pdf():
        Logger.log(f'Downloading PDF({file_name}).', Importance.INFO)
        response = requests.get(download_url)
        with open(file_path,'wb+') as file:
            file.write(response.content)
        Logger.log(f'Finished downloading and saving PDF({file_name}).', Importance.INFO)

    if no_dl:
        Logger.log(f'[NO DOWNLOAD] PDF({file_name}) download forcibly skipped.', Importance.INFO)
        return file_path

    if os.path.exists(file_path):
        if OVERWRITE_ALL_PDF:
            Logger.log(f'PDF({file_name}) already exists. Overwriting.', Importance.INFO)
            download_pdf()
        else:
            Logger.log(f'PDF({file_name}) already exists. Skipping download.', Importance.INFO)
    else:
        os.makedirs(''.join(file_path.split('/')[:-1]), exist_ok=True)
        Logger.log(f'PDF({file_name}) does not exist. Downloading.', Importance.INFO)
        download_pdf()
    return file_path


# process given PDFdata
def process_pdf(pdf_data: Tuple) -> None:
    try:
        year, semester, college = pdf_data
        pdflink = PDF_BASE_LINK.format(year+semester, college)
        pdf_file_path = load_pdf(pdflink, no_dl=(year in LEGACY_YEAR_DATA))
        grades_list = PDFParser.parse_grades_pdf(pdf_file_path)
        DatabaseHandler.add_grade_entries('tamugrades', grades_list)
    except Exception:
        pdf_name = pdf_file_path.split('/')[-1]
        Logger.log(f'Unable to parse PDF({pdf_name})', Importance.WARN)


# main
def main() -> None:
    # complete startup tasks
    Utils.startup()
    print('Check the latest log file to see database build progress')
    DatabaseHandler.send_query('CREATE TABLE IF NOT EXISTS tamugrades ('
        +'year SMALLINT(4),'
        +'semester VARCHAR(6),'
        +'college VARCHAR(7),'
        +'departmentName VARCHAR(5),'
        +'course VARCHAR(4),'
        +'section VARCHAR(3),'
        +'honors TINYINT(1),'
        +'avgGPA FLOAT(4,3),'
        +'professorName VARCHAR(30),'
        +'numA SMALLINT(3),'
        +'numB SMALLINT(3),'
        +'numC SMALLINT(3),'
        +'numD SMALLINT(3),'
        +'numF SMALLINT(3),'
        +'numI SMALLINT(3),'
        +'numS SMALLINT(3),'
        +'numU SMALLINT(3),'
        +'numQ SMALLINT(3),'
        +'numX SMALLINT(3)'
        +');')
    DatabaseHandler.send_query('CREATE TABLE IF NOT EXISTS status ('
        +'item VARCHAR(10),'
        +'value BOOLEAN'
        +');')
    DatabaseHandler.send_query('TRUNCATE TABLE tamugrades;')

    with alive_bar(total=1,title='Scraping metadata') as progress_bar:
        semesters = ['1','2','3']
        years, colleges = scrape_report_metadata()
        years = years+LEGACY_YEAR_DATA
        blacklist = ['AE','AP','GV','QT','UT','DN_PROF','SL_PROF','MD_PROF','CP_PROF','VM_PROF']
        colleges = list(set(colleges) - set(blacklist))
        # AE=Academic Success Center
        # AP=Association Provost For UG Studies
        # GV=TAMU-Galveston
        # QT=TAMU-Qatar
        # UT=University Totals
        # PROF=Professional, format not yet supported
        progress_bar(1.0) # pylint: disable=not-callable

    num_pdfs = len(years)*len(semesters)*len(colleges)
    with alive_bar(total=num_pdfs,dual_line=True,title='Building database') as progress_bar:
        # generate pdf urls
        pdf_data = []
        for year in years[::-1]:
            for semester in semesters:
                for college in colleges:
                    pdf_data.append([year,semester,college])

        # automatically load pdfs from pdfs list
        try:
            sem = ['SPRING','SUMMER','FALL']
            for pdf in pdf_data:
                progress_bar.text = f'  -> Processing: {pdf[0]} {sem[int(pdf[1])-1]} {pdf[2]}'
                process_pdf(pdf)
                progress_bar() # pylint: disable=not-callable
                DatabaseHandler.set_sync_percentage(round(progress_bar.current()/num_pdfs*100))
        except KeyboardInterrupt:
            Logger.log('KeyboardInterrupt recieved: Exiting', importance=None)
            Utils.shutdown()
            sys.exit(1)
        else:
            Utils.shutdown()


if __name__ == "__main__":
    main()
