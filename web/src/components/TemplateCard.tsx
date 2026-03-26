import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import ImageLink from './ImageLink.tsx'
import UserBaseInfo from './UserBaseInfo.tsx'
import TemplateThumbnail from './TemplateThumbnail.tsx'
import UserBaseInfoAside from './UserBaseInfoAside.tsx'
import CreatorLink from './CreatorLink.tsx'


    
// Component

        function TemplateCard({
            imgId,
            useCustomUserInfo,
            userDataId,
            imageLinkId,
            title,
            creatorName
        }: {
            imgId: string;
            useCustomUserInfo?: boolean;
            userDataId?: string;
            imageLinkId?: string;
            title?: string;
            creatorName?: string;
        }) {
            return (
                <section>
                    <div className={"analyticsScrollPoint_analyticsScrollPoint__EZ4T_"}>
                    </div>
                    <div className={"TemplateModal_modalTrigger__Oe4dT"}>
                        <TemplateThumbnail imgId={imgId} />
                    </div>
                    <div className={"Spacer_spacer__Hz1_q"} style={{ minHeight: "8px" }}>
                    </div>
                    <div className={"UserBaseInfo_container__72ryf"}>
                        <div className={"UserBaseInfo_userInfoContainer__UAQc_"}>
                            {useCustomUserInfo ? (
                                <CustomUserInfo
                                    imageLinkId={imageLinkId as string}
                                    title={title as string}
                                    creatorName={creatorName as string}
                                />
                            ) : (
                                <DefaultUserInfo userDataId={userDataId as string} />
                            )}
                        </div>
                        <UserBaseInfoAside />
                    </div>
                </section>
            );
        }
    

// Subcomponents

        function DefaultUserInfo({ userDataId }: { userDataId: string }) {
            return <UserBaseInfo dataId={userDataId} />;
        }

        function CustomUserInfo({
            imageLinkId,
            title,
            creatorName
        }: {
            imageLinkId: string;
            title: string;
            creatorName: string;
        }) {
            return (
                <>
                    <picture
                        className={"UserBaseInfo_userImage__uwxh7"}
                        style={{ "--image-size": "36px" } as React.CSSProperties}
                    >
                        <ImageLink imgId={imageLinkId} />
                    </picture>
                    <section className={"UserBaseInfo_textInfoContainer__JNjgO"}>
                        <p
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-150-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-150-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-150-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-150-regular-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            <a>
                                {title}
                            </a>
                        </p>
                        <p
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-50-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-50-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-50-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-50-regular-letter-spacing)",
                                "--typography-color": "var(--color-gray-400)"
                            } as React.CSSProperties}
                        >
                            <CreatorLink name={creatorName} />
                        </p>
                    </section>
                </>
            );
        }
    

export default TemplateCard
