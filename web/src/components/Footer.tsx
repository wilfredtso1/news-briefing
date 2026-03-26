import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Notion_logo from './icons/Notion_logo.tsx'
import NotionLogoLink from './NotionLogoLink.tsx'
import LanguagePickerButton from './LanguagePickerButton.tsx'
import FooterTextButton from './FooterTextButton.tsx'
import FooterSocialList from './FooterSocialList.tsx'
import FooterColumn from './FooterColumn.tsx'


// Component

        function Footer({ year }: { year: number }) {
            return (
                <nav className={"footer_footerInner__MQQSo"}>
                    <div className={"footer_footerTop__rz2e9"}>
                        <div>
                            <NotionLogoLink
                                className="footer_logo__ssDpx"
                                logo={<Notion_logo />}
                            />
                        </div>
                        <div className={"footer_footerTopMain__2yt5M"}>
                            <FooterSocialList />
                            <div className={"footer_addendum__i1N2u"}>
                                <div className={"languagePicker_languagePicker__7tXbz"}>
                                    <LanguagePickerButton buttonId=":r9:" label="English (US)" />
                                </div>
                                <div
                                    className={"Spacer_spacer__Hz1_q"}
                                    style={{ minHeight: "8px" }}
                                >
                                </div>
                                <FooterTextButton
                                    label="Do Not Sell or Share My Info"
                                    buttonClass="footerDoNotSell_button__MLFsR}"
                                />
                                <FooterTextButton
                                    label="Cookie settings"
                                    buttonClass="footer_button__vbjiT"
                                />
                                <div
                                    className={"Spacer_spacer__Hz1_q"}
                                    style={{ minHeight: "8px" }}
                                >
                                </div>
                                <span
                                    className={"typography_typography__Exx2D footer_copyright__WXbFd"}
                                    style={{
                                        "--typography-font": "var(--typography-sans-100-regular-font)",
                                        "--typography-font-sm": "var(--typography-sans-100-regular-font)",
                                        "--typography-letter-spacing": "var(--typography-sans-100-regular-letter-spacing)",
                                        "--typography-letter-spacing-sm": "var(--typography-sans-100-regular-letter-spacing)",
                                        "--typography-color": "inherit"
                                    } as React.CSSProperties}
                                >
                                    © {year} Notion Labs, Inc.
                                </span>
                            </div>
                        </div>
                    </div>
                    <div className={"footer_footerBottom__sYaND"}>
                        <div className={"footer_footerColumns__T50DJ"}>
                            <FooterColumn dataId="0" />
                            <FooterColumn dataId="1" />
                            <FooterColumn dataId="2" />
                            <FooterColumn dataId="3" />
                        </div>
                    </div>
                </nav>
            );
        }
    

export default Footer
