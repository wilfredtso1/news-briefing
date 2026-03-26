import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import ImageLink from './ImageLink.tsx'
import UserBaseInfo from './UserBaseInfo.tsx'
import ButtonLink from './ButtonLink.tsx'
import PrimaryActionButton from './PrimaryActionButton.tsx'


// Component

        function TemplateHeader({
            title
        }: {
            title: string;
        }) {
            return (
                <header className={"template_templateHeader___GL6l"}>
                    <span className={"template_templateHeaderContainer__yGFxj"}>
                        <span className={"template_templateHeaderLeft__3fnxN"}>
                            <h1
                                className={"typography_typography__Exx2D heading_heading__OmVf6"}
                                style={{
                                    "--typography-font": "var(--typography-sans-600-bold-font)",
                                    "--typography-font-sm": "var(--typography-sans-700-bold-font)",
                                    "--typography-letter-spacing": "var(--typography-sans-600-bold-letter-spacing)",
                                    "--typography-letter-spacing-sm": "var(--typography-sans-700-bold-letter-spacing)",
                                    "--typography-color": "inherit"
                                } as React.CSSProperties}
                            >
                                {title}
                            </h1>
                            <div className={"UserBaseInfo_container__72ryf"}>
                                <div className={"UserBaseInfo_userInfoContainer__UAQc_"}>
                                    <picture
                                        className={"UserBaseInfo_userImage__uwxh7"}
                                        style={{ "--image-size": "36px" } as React.CSSProperties}
                                    >
                                        <ImageLink imgId="0" />
                                    </picture>
                                    <UserBaseInfo dataId="0" />
                                </div>
                            </div>
                        </span>
                        <div className={"template_templateCtaContainer__2jAR2"}>
                            <span className={"template_templateHeaderCta__2Fnch"}>
                                <div className={"templateViewCta_templatePageCtaContainer__F2nxk"}>
                                    <ButtonLink
                                        label="View template"
                                        variant="template"
                                        rel="noopener"
                                        target="_blank"
                                    />
                                </div>
                            </span>
                            <span className={"template_templateHeaderCta__2Fnch"}>
                                <div className={"templateDuplicateCta_templatePageCtaContainer__9CLyb"}>
                                    <PrimaryActionButton label="Get template" />
                                </div>
                            </span>
                        </div>
                    </span>
                </header>
            );
        }
    

export default TemplateHeader
