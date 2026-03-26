import React from 'react'
import type { JSX } from 'react/jsx-runtime'



        type UserBaseInfoData = {
            title?: string;
            secondaryLinkText?: string;
            metaName?: string;
            metaDate?: string;
        }
    
// Component

        function UserBaseInfo({
            dataId
        }: {
            dataId: string;
        }) {
            const {
                title,
                secondaryLinkText,
                metaName,
                metaDate
            }: UserBaseInfoData = getUserBaseInfoData(dataId);

            return (
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
                        {title ? (
                            <a>
                                {title}
                            </a>
                        ) : null}
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
                        {secondaryLinkText ? (
                            <a style={{ color: "inherit", textDecoration: "none" }}>
                                {secondaryLinkText}
                            </a>
                        ) : metaName && metaDate ? (
                            <span
                                className={"typography_typography__Exx2D"}
                                style={{
                                    "--typography-font": "var(--typography-sans-50-regular-font)",
                                    "--typography-font-sm": "var(--typography-sans-50-regular-font)",
                                    "--typography-letter-spacing": "var(--typography-sans-50-regular-letter-spacing)",
                                    "--typography-letter-spacing-sm": "var(--typography-sans-50-regular-letter-spacing)",
                                    "--typography-color": "var(--color-gray-500)"
                                } as React.CSSProperties}
                            >
                                {`${metaName} · `}
                                {metaDate}
                            </span>
                        ) : null}
                    </p>
                </section>
            );
        }
    


        function getUserBaseInfoData(id: string): UserBaseInfoData {
            const key = String(id);
            const data: Record<string, UserBaseInfoData> = {
                "0": {
                    title: "Notion",
                    secondaryLinkText: "521 templates"
                },
                "1": {
                    metaName: "Samuel Rodriguez",
                    metaDate: "Feb 19, 2026"
                },
                "2": {
                    metaName: "Jared",
                    metaDate: "Apr 17, 2025"
                },
                "3": {
                    metaName: "Cam Vacek",
                    metaDate: "Dec 6, 2024"
                },
                "4": {
                    title: "Wellness pack"
                },
                "5": {
                    title: "Events Calendar"
                },
                "6": {
                    title: "Productivity pack"
                }
            };

            return data[key] || {};
        }
    

export default UserBaseInfo
